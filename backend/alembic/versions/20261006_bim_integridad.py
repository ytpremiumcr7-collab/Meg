"""Protect IFC element identity and BIM budget links without deleting historical evidence."""
from alembic import op
import sqlalchemy as sa

revision = '20261006_bim_integridad'
down_revision = '20261005_ingesta_inegi'
branch_labels = None
depends_on = None


def upgrade():
    # Historical conflicts require an explicit repair, never pick a mapping silently.
    bind = op.get_bind()
    duplicates = bind.execute(sa.text('SELECT modelo_id, global_id FROM elementos_bim GROUP BY modelo_id, global_id HAVING count(*) > 1 LIMIT 1')).first()
    invalid = bind.execute(sa.text('''SELECT e.id FROM elementos_bim e
        JOIN modelos_bim m ON m.id=e.modelo_id JOIN partidas p ON p.id=e.partida_id
        JOIN presupuestos b ON b.id=p.presupuesto_id
        WHERE m.tenant_id<>b.tenant_id OR m.expediente_id<>b.expediente_id LIMIT 1''')).first()
    if duplicates or invalid:
        raise RuntimeError('BIM histórico inconsistente: reparar duplicados/enlaces con respaldo antes de aplicar esta migración')
    op.create_foreign_key('fk_modelobim_tenant_expediente', 'modelos_bim', 'expedientes_obra',
        ['tenant_id', 'expediente_id'], ['tenant_id', 'id'])
    op.create_unique_constraint('uq_elementobim_modelo_global', 'elementos_bim', ['modelo_id', 'global_id'])
    op.execute('''CREATE FUNCTION bim_validar_enlaces() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (SELECT 1 FROM elementos_bim e JOIN modelos_bim m ON m.id=e.modelo_id
            JOIN partidas p ON p.id=e.partida_id JOIN presupuestos b ON b.id=p.presupuesto_id
            WHERE m.tenant_id<>b.tenant_id OR m.tenant_id<>p.tenant_id OR m.expediente_id<>b.expediente_id) THEN
            RAISE EXCEPTION 'BIM: partida fuera del tenant o expediente' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
    END; $$''')
    for table in ['elementos_bim', 'modelos_bim', 'partidas', 'presupuestos']:
        op.execute(f'''CREATE CONSTRAINT TRIGGER tr_{table}_bim_enlace
            AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY IMMEDIATE
            FOR EACH ROW EXECUTE FUNCTION bim_validar_enlaces()''')


def downgrade():
    for table in ['elementos_bim', 'modelos_bim', 'partidas', 'presupuestos']:
        op.execute(f'DROP TRIGGER tr_{table}_bim_enlace ON {table}')
    op.execute('DROP FUNCTION bim_validar_enlaces()')
    op.drop_constraint('fk_modelobim_tenant_expediente', 'modelos_bim', type_='foreignkey')
    op.drop_constraint('uq_elementobim_modelo_global', 'elementos_bim', type_='unique')
