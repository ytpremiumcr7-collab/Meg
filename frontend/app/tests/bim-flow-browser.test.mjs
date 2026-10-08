// Real browser/API/PostGIS/Redis/worker/filesystem flow. No intercepted routes.
import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createWriteStream } from 'node:fs';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { chromium } from 'playwright';

const frontend = resolve('.');
const backend = resolve('../../backend');
const evidence = resolve(process.env.BIM_EVIDENCE_DIR || 'bim-browser-evidence');
const origin = 'http://127.0.0.1:4173';
const apiOrigin = 'http://127.0.0.1:8000';
let browser, api, worker, dispatcher, preview, credentials;
const processes = [];
const env = { ...process.env, CORS_ALLOWED_ORIGINS: JSON.stringify([origin]),
  BIM_STORAGE_PROVIDER:'filesystem', BIM_LOCAL_STORAGE_PATH:join(evidence, 'files'),
  OTEL_EXPORTER_OTLP_ENDPOINT:'' };

function start(name, command, args, cwd) {
  const log = createWriteStream(join(evidence, `${name}.log`), { flags:'a' });
  const process = spawn(command, args, { cwd, env, stdio:['ignore','pipe','pipe'] });
  process.stdout.pipe(log, {end:false});
  process.stderr.pipe(log, {end:false});
  process.on('close',()=>log.end());
  process.on('error', e => log.write(String(e)));
  processes.push(process);
  return process;
}
function startApi() { return start('api', join(backend,'.venv/bin/python'),
  ['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--no-access-log'], backend); }
function startWorker() { return start('worker', join(backend,'.venv/bin/python'),
  ['-m','celery','-A','app.workers.celery_app','worker','--pool=solo','--loglevel=INFO'], backend); }
async function stop(process) {
  if (!process || process.exitCode !== null) return;
  const finished = once(process, 'exit');
  process.kill('SIGTERM');
  const timeout = setTimeout(() => process.kill('SIGKILL'), 10000);
  await finished; clearTimeout(timeout);
}
async function ready(url, process) {
  for (let attempt=0;attempt<180;attempt++) {
    if (process.exitCode !== null) throw new Error(`Service stopped before readiness: ${url}`);
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve,500));
  }
  throw new Error(`Service never became ready: ${url}`);
}
async function login(page, email) {
  await page.goto(origin);
  await page.getByPlaceholder('tu@correo.com').fill(email);
  await page.locator('input[type="password"]').fill(credentials.password);
  await page.getByRole('button',{name:'Entrar al Sistema'}).click();
  await page.getByRole('navigation').getByRole('button',{name:'Proyectos',exact:true}).waitFor({timeout:60000});
}

before(async () => {
  await mkdir(evidence,{recursive:true});
  credentials = JSON.parse(await readFile(process.env.BIM_ACCEPTANCE_CREDENTIALS,'utf8'));
  api=startApi(); await ready(apiOrigin+'/ready', api);
  dispatcher=start('dispatcher',join(backend,'.venv/bin/python'),['-m','app.workers.job_dispatcher'],backend);
  preview=start('preview',process.execPath,['node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','4173','--strictPort'],frontend);
  await ready(origin,preview);
  browser=await chromium.launch({ executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
    args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'] });
});

after(async () => {
  await browser?.close();
  for (const process of processes.reverse()) await stop(process);
});

test('user creates an obra, resumes an IFC job after restart, approves and exports, then opens 4D', {timeout:240000}, async () => {
  const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.tracing.start({screenshots:true,snapshots:true});
  const page=await context.newPage();
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  try {
    await login(page,credentials.reviewer);
    await page.getByRole('navigation').getByRole('button',{name:'Proyectos',exact:true}).click();
    await page.getByRole('button',{name:'Nuevo',exact:true}).click();
    await page.getByLabel('Título del expediente').fill('Obra sintética de aceptación BIM');
    await page.getByLabel('Órgano', {exact:false}).fill('CI staging');
    await page.getByLabel('Unidad administrativa').fill('Pruebas');
    await page.getByLabel('Serie documental', {exact:false}).first().fill('02100');
    await page.getByLabel('Subserie documental', {exact:false}).fill('02100-01');
    const [created]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/expedientes'),
      page.getByRole('button',{name:'Crear expediente',exact:true}).click()]);
    assert.equal(created.status(),200);
    await page.getByRole('button',{name:'Calculadora BIM',exact:true}).click();
    const [uploadResponse]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/bim\/[^/]+\/modelos$/.test(new URL(r.url()).pathname)),
      page.getByLabel('Subir archivo IFC').setInputFiles(join(backend,'tests/fixtures/ifc/wall_millimetres.ifc'))]);
    assert.equal(uploadResponse.status(),200);
    const model=await uploadResponse.json();
    assert.equal(model.estado_procesamiento,'PENDIENTE');
    // Worker was never started. Restarting both API and dispatcher must retain work.
    await stop(api); await stop(dispatcher);
    api=startApi(); await ready(apiOrigin+'/ready',api);
    dispatcher=start('dispatcher',join(backend,'.venv/bin/python'),['-m','app.workers.job_dispatcher'],backend);
    await page.reload();
    worker=startWorker();
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).waitFor({timeout:60000});
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='2. Preparar presupuesto'&&!b.disabled),{},{timeout:60000});
    await page.screenshot({path:join(evidence,'01-modelo-recuperado.png'),fullPage:true});
    const apiModel=await page.request.get(`${apiOrigin}/api/v1/bim/${model.expediente_id}/modelos/${model.id}/elementos?incluir_malla=true`);
    assert.equal(apiModel.status(),200);
    const elements=await apiModel.json(); assert.equal(elements.length,1);
    assert.equal(elements[0].volumen,2.4); assert.ok(elements[0].malla_vertices.length>0);
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).click();
    await page.getByPlaceholder('Buscar en catálogo (ej. muro, concreto)...').fill('Muro de prueba');
    const [catalogResponse]=await Promise.all([
      page.waitForResponse(r=>r.url().includes('/api/v1/catalogo-apu?')&&r.request().method()==='GET'),
      page.getByRole('button',{name:'Buscar concepto para IfcWall'}).click(),
    ]);
    assert.equal(catalogResponse.status(),200);
    await page.getByRole('button',{name:/Muro de prueba sintética CI/}).click();
    await page.getByPlaceholder('Fuente: contrato, convocatoria o análisis').fill('Prueba sintética CI: factores cero explícitos');
    await page.getByRole('button',{name:'Generar presupuesto',exact:true}).click();
    await page.getByRole('button',{name:'Validar presupuesto'}).waitFor();
    await page.getByRole('button',{name:'Validar presupuesto'}).click();
    await page.getByRole('button',{name:'Aprobar presupuesto'}).click();
    await page.getByText('Estado: APROBADO',{exact:true}).waitFor();
    await page.getByRole('region',{name:'Revisión del presupuesto'}).getByText('$300.00',{exact:true}).first().waitFor();
    await page.screenshot({path:join(evidence,'02-presupuesto-aprobado.png'),fullPage:true});
    for (const format of ['Excel','PDF']) {
      const event=page.waitForEvent('download');
      await page.getByRole('button',{name:`Descargar ${format}`}).click();
      const download=await event;
      const destination=join(evidence,download.suggestedFilename());
      await download.saveAs(destination);
      const bytes=await readFile(destination);
      assert.ok(bytes.length>500);
      assert.equal(bytes.subarray(0,format==='PDF'?4:2).toString(),format==='PDF'?'%PDF':'PK');
    }
    // The target must still open correctly when it falls outside the first 20 programs.
    const fixtures=start('schedule-fixtures',join(backend,'.venv/bin/python'),
      ['-m','scripts.seed_bim_acceptance_ci','--programs-for',model.expediente_id],backend);
    const [fixtureExit]=await once(fixtures,'exit');
    assert.equal(fixtureExit,0);
    await page.getByRole('button',{name:'3. Crear cronograma'}).click();
    await page.locator('input[type="date"]').fill('2026-10-06');
    await page.getByRole('button',{name:'Generar cronograma 4D',exact:true}).click();
    await page.getByRole('button',{name:'Abrir cronograma en Programación'}).waitFor({timeout:60000});
    await page.reload(); // 4D history is recovered too, not only transient component state.
    await page.getByRole('button',{name:'3. Crear cronograma'}).click();
    await page.getByRole('button',{name:'Abrir cronograma en Programación'}).click();
    const scheduleId=new URL(page.url()).searchParams.get('programa');
    assert.ok(scheduleId);
    await page.waitForFunction(id=>document.querySelector('select[aria-label="Cronograma de esta obra"]')?.value===id,scheduleId);
    await page.screenshot({path:join(evidence,'03-cronograma.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'Calculadora BIM',exact:true}).click();
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).click();
    await page.getByText('Estado: APROBADO',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    await page.screenshot({path:join(evidence,'04-movil.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    // A genuine IFC contains one measurable wall and another without QTO/shape.
    await page.setViewportSize({width:1440,height:1000});
    await page.getByLabel('Subir archivo IFC').setInputFiles(credentials.partial_ifc);
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='2. Preparar presupuesto'&&!b.disabled),{},{timeout:60000});
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).click();
    const missing=page.getByRole('region',{name:'Completar mediciones faltantes'});
    await missing.waitFor();
    // Select the m3 catalogue for this model too; captures must use its unit.
    if (await page.getByPlaceholder('Buscar en catálogo (ej. muro, concreto)...').count()) {
      await page.getByPlaceholder('Buscar en catálogo (ej. muro, concreto)...').fill('Muro de prueba');
      const [catalogResponse]=await Promise.all([
        page.waitForResponse(r=>r.url().includes('/api/v1/catalogo-apu?')&&r.request().method()==='GET'),
        page.getByRole('button',{name:'Buscar concepto para IfcWall'}).click(),
      ]);
      assert.equal(catalogResponse.status(),200);
      await page.getByRole('button',{name:/Muro de prueba sintética CI/}).click();
    }
    await page.getByPlaceholder('Fuente: contrato, convocatoria o análisis').fill('Prueba parcial: factores cero explícitos');
    await page.getByRole('button',{name:'Generar presupuesto',exact:true}).click();
    const budgetReview=page.getByRole('region',{name:'Revisión del presupuesto'});
    await budgetReview.getByText(/Presupuesto PARCIAL: 1 de 2 elementos medidos/).waitFor();
    await budgetReview.getByText('$300.00',{exact:true}).first().waitFor();
    assert.equal(await budgetReview.getByRole('button',{name:'Confirmar cálculo'}).isDisabled(),true);
    await page.screenshot({path:join(evidence,'06-presupuesto-parcial.png'),fullPage:true});
    await missing.getByLabel('Cantidad faltante (m3)',{exact:true}).fill('1.6');
    await missing.getByLabel('Referencia de la medición',{exact:true}).fill('Levantamiento de prueba revisado');
    await page.getByRole('button',{name:'Generar presupuesto',exact:true}).click();
    await budgetReview.getByText(/Mediciones completas: 2 de 2 elementos medidos/).waitFor();
    await budgetReview.getByText('$500.00',{exact:true}).first().waitFor();
    await page.screenshot({path:join(evidence,'07-mediciones-completadas.png'),fullPage:true});
    const readerContext=await browser.newContext({viewport:{width:1440,height:1000}});
    try {
      const readerPage=await readerContext.newPage();
      await login(readerPage,credentials.reader);
      await readerPage.getByRole('navigation').getByRole('button',{name:'Proyectos',exact:true}).click();
      await readerPage.getByRole('button',{name:/Obra sintética de aceptación BIM/}).click();
      await readerPage.getByRole('button',{name:'Calculadora BIM',exact:true}).click();
      await readerPage.getByLabel('Subir archivo IFC').waitFor({state:'attached'});
      assert.equal(await readerPage.getByLabel('Subir archivo IFC').isDisabled(),true);
      await readerPage.screenshot({path:join(evidence,'05-solo-lectura.png'),fullPage:true});
    } finally { await readerContext.close(); }
    await page.goto(origin+'/?app=topografia');
    await page.getByRole('button',{name:'Levantamiento',exact:true}).click();
    await page.getByPlaceholder('Nombre nuevo levantamiento').fill('Aceptación UTM en metros');
    await page.getByLabel('Sistema de coordenadas').selectOption('32614');
    const [surveyCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/topografia\/[^/]+\/levantamientos$/.test(new URL(r.url()).pathname)),
      page.getByRole('button',{name:'Crear levantamiento',exact:true}).click()]);
    assert.equal(surveyCreated.status(),200);
    const survey=await surveyCreated.json();
    assert.equal(survey.crs,'EPSG:32614');
    const [tinCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/triangular$/.test(new URL(r.url()).pathname)),
      page.getByLabel('Subir puntos CSV').setInputFiles({name:'terreno.csv',mimeType:'text/csv',
        buffer:Buffer.from('P1,500000,2200000,1\nP2,500001,2200000,-1\nP3,500000,2200001,-1\n')})]);
    assert.equal(tinCreated.status(),200);
    const tin=await tinCreated.json();
    await page.getByLabel('Superficie existente').selectOption(tin.id);
    await page.getByLabel('Elevación de referencia').fill('0');
    const [volumeCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/topografia/volumenes'),
      page.getByRole('button',{name:'Calcular',exact:true}).click()]);
    assert.equal(volumeCreated.status(),200);
    const volume=await volumeCreated.json();
    assert.equal(volume.volumen_corte_m3,.042);
    assert.equal(volume.volumen_terraplen_m3,.208);
    assert.equal(volume.evidencia.cobertura.completa,true);
    await page.getByRole('button',{name:'Generar presupuesto de movimiento de tierras',exact:true}).waitFor();
    await page.getByLabel('Referencia de parámetros topográficos').fill('CI: revisión sintética del terreno');
    const [earthBudgetResponse] = await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/topografia\/[^/]+\/volumenes\/[^/]+\/generar-presupuesto$/.test(new URL(r.url()).pathname)),
      page.getByRole('button',{name:'Generar presupuesto de movimiento de tierras',exact:true}).click()]);
    assert.equal(earthBudgetResponse.status(),200,await earthBudgetResponse.text());
    const earthBudget = await earthBudgetResponse.json();
    assert.equal(earthBudget.partidas.length,2);
    assert.ok(earthBudget.partidas.every(p=>p.metadatos.topografia.calculo_id===volume.id));
    const earthReview=page.getByRole('region',{name:'Revisión del presupuesto'});
    for (const number of [1,2]) {
      await earthReview.getByLabel(`Buscar concepto para partida ${number}`).fill('CI-EARTHWORK');
      const select=earthReview.getByLabel(`Concepto para partida ${number}`);
      await select.locator('option').filter({hasText:'Movimiento de tierras sintético CI'}).waitFor({state:'attached'});
      const option=await select.locator('option').filter({hasText:'Movimiento de tierras sintético CI'}).getAttribute('value');
      await select.selectOption(option);
      const [priced] = await Promise.all([
        page.waitForResponse(r=>r.request().method()==='PUT' && /\/partidas\/[^/]+\/catalogo$/.test(new URL(r.url()).pathname)),
        earthReview.getByRole('button',{name:`Asignar concepto a partida ${number}`,exact:true}).click()]);
      assert.equal(priced.status(),200);
      const result=await priced.json();
      assert.ok(result.partidas.every(p=>p.metadatos.topografia.calculo_id===volume.id));
    }
    await earthReview.getByRole('status').filter({hasText:'Estado: CALCULADO'}).waitFor();
    await earthReview.getByRole('button',{name:'Validar presupuesto',exact:true}).click();
    await earthReview.getByRole('status').filter({hasText:'Estado: VALIDADO'}).waitFor();
    await earthReview.getByRole('button',{name:'Aprobar presupuesto',exact:true}).click();
    await earthReview.getByRole('status').filter({hasText:'Estado: APROBADO'}).waitFor();
    const [earthDownload]=await Promise.all([page.waitForEvent('download'),earthReview.getByRole('button',{name:'Descargar Excel',exact:true}).click()]);
    await earthDownload.saveAs(join(evidence,'earthwork-budget.xlsx'));
    await page.screenshot({path:join(evidence,'10-topografia-utm.png'),fullPage:true});
    await page.getByLabel('Elevación de referencia').fill('1');
    assert.equal(await page.getByRole('button',{name:'Generar presupuesto de movimiento de tierras',exact:true}).count(),0);
    await page.getByPlaceholder('Nombre nuevo levantamiento').fill('Otro levantamiento UTM 15');
    await page.getByLabel('Sistema de coordenadas').selectOption('32615');
    const [secondSurveyCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/topografia\/[^/]+\/levantamientos$/.test(new URL(r.url()).pathname)),
      page.getByRole('button',{name:'Crear levantamiento',exact:true}).click()]);
    assert.equal(secondSurveyCreated.status(),200);
    await page.getByRole('button',{name:'Calcular',exact:true}).waitFor({state:'hidden'});
    assert.equal(await page.getByRole('button',{name:'Calcular',exact:true}).count(),0);
    await page.getByLabel('Levantamiento activo').selectOption(survey.id);
    await page.getByLabel('Superficie existente').waitFor();
    assert.equal(await page.getByLabel('Superficie existente').inputValue(),'');
    assert.equal(await page.getByRole('button',{name:'Calcular',exact:true}).isDisabled(),true);
    const projects = start('project-fixtures', join(backend,'.venv/bin/python'),
      ['-m','scripts.seed_bim_acceptance_ci','--projects-after',model.expediente_id],backend);
    const [projectsExit]=await once(projects,'exit');
    assert.equal(projectsExit,0);
    await page.goto(origin+'/?app=megalodon-costos');
    await page.getByRole('button',{name:'Presupuesto',exact:true}).click();
    await page.getByRole('button',{name:'Actualizar material',exact:true}).click();
    await page.getByText('Catálogos en la base conectada',{exact:true}).click();
    await page.getByText('CI sintético: catálogo de aceptación',{exact:false}).waitFor();
    await page.getByLabel('Material revisado',{exact:true}).selectOption(credentials.indexed_material);
    await page.getByLabel('Fecha de corte de publicaciones',{exact:true}).fill('2020-09-10');
    await page.getByRole('button',{name:'Usar última publicación disponible',exact:true}).click();
    await page.getByText('Variación observada: 15.0000% · corte 2020-09-10.',{exact:true}).waitFor();
    await page.getByText('Original: $100.0000 MXN · Estimado: $115.00 MXN/kg sin IVA.',{exact:true}).waitFor();
    await page.screenshot({path:join(evidence,'08-catalogos-indices.png'),fullPage:true});
    await page.goto(origin+'/?app=legl-consultor');
    await page.getByText('969 artículos consultables · ver cobertura',{exact:true}).click();
    await page.getByText('Documentos sin artículos consultables: Manual Comité Adquisiciones.',{exact:true}).waitFor();
    await page.screenshot({path:join(evidence,'09-cobertura-corpus.png'),fullPage:true});
    assert.deepEqual(errors,[]);

  } finally {
    await page.screenshot({path:join(evidence,'last-screen.png'),fullPage:true}).catch(()=>{});
    await context.tracing.stop({path:join(evidence,'bim-flow-trace.zip')});
    await context.close();
  }
});
