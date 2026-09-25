/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

// =============================================================================
// Megalodon CostOS — BIM Price Catalog (Synthetic Construction Prices)
// =============================================================================

export interface CatalogElement {
  key: string;
  description: string;
  unit: string;
  unitPrice: number;
  category: 'direct' | 'indirect' | 'financing' | 'profit' | 'contingency';
  materials: ResourceLine[];
  labor: ResourceLine[];
  equipment: ResourceLine[];
}

export interface ResourceLine {
  key: string;
  description: string;
  unit: string;
  quantity: number;
  unitCost: number;
  amount: number;
}

/** Synthetic Mexican construction unit price catalog */
export const CATALOGO_CONCEPTOS: CatalogElement[] = [
  // ==== CONCRETE WORK (m3) ====
  {
    key: 'CC-HG-001',
    description: 'Concreto hidráulico f' + 'c=150 kg/cm², vaciado en losa',
    unit: 'm3',
    unitPrice: 2847.50,
    category: 'direct',
    materials: [
      { key: 'MAT-001', description: 'Cemento Portland CPC 30R', unit: 'ton', quantity: 0.325, unitCost: 4200.00, amount: 1365.00 },
      { key: 'MAT-002', description: 'Arena cribada', unit: 'm3', quantity: 0.52, unitCost: 320.00, amount: 166.40 },
      { key: 'MAT-003', description: 'Grava de 3/4"', unit: 'm3', quantity: 0.72, unitCost: 380.00, amount: 273.60 },
      { key: 'MAT-004', description: 'Agua potable', unit: 'm3', quantity: 0.20, unitCost: 42.50, amount: 8.50 },
    ],
    labor: [
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 4.0, unitCost: 52.35, amount: 209.40 },
      { key: 'MAN-002', description: 'Operario albañil', unit: 'hr', quantity: 3.5, unitCost: 78.50, amount: 274.75 },
      { key: 'MAN-003', description: 'Oficial armador', unit: 'hr', quantity: 1.0, unitCost: 95.00, amount: 95.00 },
    ],
    equipment: [
      { key: 'EQ-001', description: 'Revolvedora de concreto 9 ft³', unit: 'hr', quantity: 1.0, unitCost: 85.50, amount: 85.50 },
      { key: 'EQ-002', description: 'Vibrador de concreto', unit: 'hr', quantity: 0.8, unitCost: 62.00, amount: 49.60 },
    ],
  },
  {
    key: 'CC-HG-002',
    description: 'Concreto hidráulico f' + 'c=200 kg/cm², columnas',
    unit: 'm3',
    unitPrice: 3215.80,
    category: 'direct',
    materials: [
      { key: 'MAT-001', description: 'Cemento Portland CPC 30R', unit: 'ton', quantity: 0.380, unitCost: 4200.00, amount: 1596.00 },
      { key: 'MAT-002', description: 'Arena cribada', unit: 'm3', quantity: 0.48, unitCost: 320.00, amount: 153.60 },
      { key: 'MAT-003', description: 'Grava de 3/4"', unit: 'm3', quantity: 0.70, unitCost: 380.00, amount: 266.00 },
      { key: 'MAT-004', description: 'Agua potable', unit: 'm3', quantity: 0.22, unitCost: 42.50, amount: 9.35 },
    ],
    labor: [
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 5.0, unitCost: 52.35, amount: 261.75 },
      { key: 'MAN-002', description: 'Operario albañil', unit: 'hr', quantity: 4.0, unitCost: 78.50, amount: 314.00 },
      { key: 'MAN-003', description: 'Oficial armador', unit: 'hr', quantity: 2.0, unitCost: 95.00, amount: 190.00 },
    ],
    equipment: [
      { key: 'EQ-001', description: 'Revolvedora de concreto 9 ft³', unit: 'hr', quantity: 1.2, unitCost: 85.50, amount: 102.60 },
      { key: 'EQ-002', description: 'Vibrador de concreto', unit: 'hr', quantity: 1.2, unitCost: 62.00, amount: 74.40 },
    ],
  },
  {
    key: 'CC-HG-003',
    description: 'Concreto hidráulico f' + 'c=250 kg/cm², zapatas',
    unit: 'm3',
    unitPrice: 3562.30,
    category: 'direct',
    materials: [
      { key: 'MAT-001', description: 'Cemento Portland CPC 40R', unit: 'ton', quantity: 0.420, unitCost: 4350.00, amount: 1827.00 },
      { key: 'MAT-002', description: 'Arena cribada', unit: 'm3', quantity: 0.45, unitCost: 320.00, amount: 144.00 },
      { key: 'MAT-003', description: 'Grava de 3/4"', unit: 'm3', quantity: 0.68, unitCost: 380.00, amount: 258.40 },
      { key: 'MAT-004', description: 'Agua potable', unit: 'm3', quantity: 0.22, unitCost: 42.50, amount: 9.35 },
    ],
    labor: [
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 4.5, unitCost: 52.35, amount: 235.58 },
      { key: 'MAN-002', description: 'Operario albañil', unit: 'hr', quantity: 3.5, unitCost: 78.50, amount: 274.75 },
      { key: 'MAN-003', description: 'Oficial armador', unit: 'hr', quantity: 1.5, unitCost: 95.00, amount: 142.50 },
    ],
    equipment: [
      { key: 'EQ-001', description: 'Revolvedora de concreto 9 ft³', unit: 'hr', quantity: 1.0, unitCost: 85.50, amount: 85.50 },
      { key: 'EQ-002', description: 'Vibrador de concreto', unit: 'hr', quantity: 1.0, unitCost: 62.00, amount: 62.00 },
    ],
  },
  // ==== STEEL REINFORCEMENT (kg) ====
  {
    key: 'ACR-HG-001',
    description: 'Acero de refuerzo Grade 42, armado en losa',
    unit: 'kg',
    unitPrice: 38.45,
    category: 'direct',
    materials: [
      { key: 'MAT-010', description: 'Varilla Grade 42 No. 3-8', unit: 'kg', quantity: 1.05, unitCost: 26.50, amount: 27.83 },
      { key: 'MAT-011', description: 'Alambre de amarre recocido #18', unit: 'kg', quantity: 0.03, unitCost: 35.00, amount: 1.05 },
    ],
    labor: [
      { key: 'MAN-003', description: 'Oficial armador', unit: 'hr', quantity: 0.08, unitCost: 95.00, amount: 7.60 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.04, unitCost: 52.35, amount: 2.09 },
    ],
    equipment: [
      { key: 'EQ-010', description: 'Herramienta menor (corta-varilla)', unit: 'hr', quantity: 0.02, unitCost: 15.00, amount: 0.30 },
    ],
  },
  {
    key: 'ACR-HG-002',
    description: 'Acero de refuerzo Grade 60, columnas y muros',
    unit: 'kg',
    unitPrice: 42.80,
    category: 'direct',
    materials: [
      { key: 'MAT-012', description: 'Varilla Grade 60 No. 4-11', unit: 'kg', quantity: 1.05, unitCost: 30.00, amount: 31.50 },
      { key: 'MAT-011', description: 'Alambre de amarre recocido #18', unit: 'kg', quantity: 0.035, unitCost: 35.00, amount: 1.23 },
    ],
    labor: [
      { key: 'MAN-003', description: 'Oficial armador', unit: 'hr', quantity: 0.09, unitCost: 95.00, amount: 8.55 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.05, unitCost: 52.35, amount: 2.62 },
    ],
    equipment: [
      { key: 'EQ-010', description: 'Herramienta menor', unit: 'hr', quantity: 0.02, unitCost: 15.00, amount: 0.30 },
    ],
  },
  // ==== MASONRY (m2) ====
  {
    key: 'MA-HG-001',
    description: 'Muro de tabique barro rojo 14x20x40 cm, colado',
    unit: 'm2',
    unitPrice: 485.60,
    category: 'direct',
    materials: [
      { key: 'MAT-020', description: 'Tabique barro rojo 14x20x40 cm', unit: 'pza', quantity: 15.0, unitCost: 18.50, amount: 277.50 },
      { key: 'MAT-021', description: 'Mortero tipo II cemento-cal-arena', unit: 'm3', quantity: 0.025, unitCost: 1850.00, amount: 46.25 },
    ],
    labor: [
      { key: 'MAN-002', description: 'Operario albañil', unit: 'hr', quantity: 1.2, unitCost: 78.50, amount: 94.20 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.8, unitCost: 52.35, amount: 41.88 },
    ],
    equipment: [
      { key: 'EQ-020', description: 'Andamio tubular', unit: 'dia', quantity: 0.05, unitCost: 35.00, amount: 1.75 },
    ],
  },
  {
    key: 'MA-HG-002',
    description: 'Muro de block de concreto 15x20x40 cm',
    unit: 'm2',
    unitPrice: 528.90,
    category: 'direct',
    materials: [
      { key: 'MAT-022', description: 'Block de concreto 15x20x40 cm', unit: 'pza', quantity: 13.5, unitCost: 22.00, amount: 297.00 },
      { key: 'MAT-021', description: 'Mortero tipo II cemento-cal-arena', unit: 'm3', quantity: 0.022, unitCost: 1850.00, amount: 40.70 },
    ],
    labor: [
      { key: 'MAN-002', description: 'Operario albañil', unit: 'hr', quantity: 1.0, unitCost: 78.50, amount: 78.50 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.9, unitCost: 52.35, amount: 47.12 },
    ],
    equipment: [
      { key: 'EQ-020', description: 'Andamio tubular', unit: 'dia', quantity: 0.05, unitCost: 35.00, amount: 1.75 },
    ],
  },
  // ==== PLASTERING (m2) ====
  {
    key: 'RE-HG-001',
    description: 'Aplanado de muros, mortero cemento-arena 2 cm',
    unit: 'm2',
    unitPrice: 285.40,
    category: 'direct',
    materials: [
      { key: 'MAT-030', description: 'Cemento blanco', unit: 'kg', quantity: 12.0, unitCost: 4.20, amount: 50.40 },
      { key: 'MAT-031', description: 'Arena fina de YESO', unit: 'm3', quantity: 0.018, unitCost: 350.00, amount: 6.30 },
    ],
    labor: [
      { key: 'MAN-004', description: 'Oficial yesero', unit: 'hr', quantity: 1.5, unitCost: 85.00, amount: 127.50 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.7, unitCost: 52.35, amount: 36.65 },
    ],
    equipment: [
      { key: 'EQ-030', description: 'Herramienta menor de yesero', unit: 'hr', quantity: 0.15, unitCost: 12.00, amount: 1.80 },
    ],
  },
  // ==== FLOORING (m2) ====
  {
    key: 'PI-HG-001',
    description: 'Piso de loseta cerámica 30x30 cm, pegada con cemento',
    unit: 'm2',
    unitPrice: 625.80,
    category: 'direct',
    materials: [
      { key: 'MAT-040', description: 'Loseta cerámica 30x30 cm tipo rústica', unit: 'pza', quantity: 12.0, unitCost: 32.50, amount: 390.00 },
      { key: 'MAT-041', description: 'Pegaazulejo cemento-polymer', unit: 'kg', quantity: 4.5, unitCost: 18.50, amount: 83.25 },
      { key: 'MAT-042', description: 'Boquilla blanca', unit: 'kg', quantity: 0.8, unitCost: 22.00, amount: 17.60 },
    ],
    labor: [
      { key: 'MAN-005', description: 'Oficial albañil especializado', unit: 'hr', quantity: 1.2, unitCost: 88.00, amount: 105.60 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.6, unitCost: 52.35, amount: 31.41 },
    ],
    equipment: [
      { key: 'EQ-030', description: 'Herramienta menor', unit: 'hr', quantity: 0.12, unitCost: 12.00, amount: 1.44 },
    ],
  },
  // ==== PAINTING (m2) ====
  {
    key: 'PN-HG-001',
    description: 'Pintura vinílica latex en muros, 2 manos',
    unit: 'm2',
    unitPrice: 185.30,
    category: 'direct',
    materials: [
      { key: 'MAT-050', description: 'Pintura vinílica base blanca', unit: 'L', quantity: 0.45, unitCost: 145.00, amount: 65.25 },
      { key: 'MAT-051', description: 'Sellador al agua', unit: 'L', quantity: 0.12, unitCost: 85.00, amount: 10.20 },
    ],
    labor: [
      { key: 'MAN-006', description: 'Oficial pintor', unit: 'hr', quantity: 0.9, unitCost: 82.00, amount: 73.80 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.4, unitCost: 52.35, amount: 20.94 },
    ],
    equipment: [
      { key: 'EQ-030', description: 'Herramienta menor', unit: 'hr', quantity: 0.1, unitCost: 12.00, amount: 1.20 },
    ],
  },
  // ==== ELECTRICAL (m2 of construction) ====
  {
    key: 'IE-HG-001',
    description: 'Instalación elécttra básica: tubería, cableado y accesorios',
    unit: 'm2',
    unitPrice: 485.00,
    category: 'direct',
    materials: [
      { key: 'MAT-060', description: 'Tubo PVC conduit pesado 3/4"', unit: 'm', quantity: 3.5, unitCost: 28.50, amount: 99.75 },
      { key: 'MAT-061', description: 'Cable THW-LS/THHW-LS Cal. 12 AWG', unit: 'm', quantity: 8.0, unitCost: 12.50, amount: 100.00 },
      { key: 'MAT-062', description: 'Caja de paso octagonal plástica', unit: 'pza', quantity: 0.5, unitCost: 25.00, amount: 12.50 },
      { key: 'MAT-063', description: 'Placa y interruptor sencillo', unit: 'pza', quantity: 0.3, unitCost: 85.00, amount: 25.50 },
    ],
    labor: [
      { key: 'MAN-007', description: 'Electricista oficial', unit: 'hr', quantity: 1.5, unitCost: 92.00, amount: 138.00 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.5, unitCost: 52.35, amount: 26.18 },
    ],
    equipment: [
      { key: 'EQ-040', description: 'Herramienta eléctrica menor', unit: 'hr', quantity: 0.1, unitCost: 18.00, amount: 1.80 },
    ],
  },
  // ==== PLUMBING (m2 of construction) ====
  {
    key: 'IH-HG-001',
    description: 'Instalación hidráulica y sanitaria básica',
    unit: 'm2',
    unitPrice: 625.50,
    category: 'direct',
    materials: [
      { key: 'MAT-070', description: 'Tubo CPVC 1/2" para agua fría', unit: 'm', quantity: 4.0, unitCost: 32.00, amount: 128.00 },
      { key: 'MAT-071', description: 'Tubo PVC sanitario 4" pesado', unit: 'm', quantity: 1.5, unitCost: 85.00, amount: 127.50 },
      { key: 'MAT-072', description: 'Codos, tees y accesorios PVC', unit: 'glb', quantity: 1.0, unitCost: 95.00, amount: 95.00 },
      { key: 'MAT-073', description: 'Lavabo con pedestal blanco', unit: 'pza', quantity: 0.04, unitCost: 1850.00, amount: 74.00 },
    ],
    labor: [
      { key: 'MAN-008', description: 'Plomero oficial', unit: 'hr', quantity: 1.8, unitCost: 95.00, amount: 171.00 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.6, unitCost: 52.35, amount: 31.41 },
    ],
    equipment: [
      { key: 'EQ-050', description: 'Herramienta de plomería menor', unit: 'hr', quantity: 0.1, unitCost: 15.00, amount: 1.50 },
    ],
  },
  // ==== DOORS & WINDOWS (pza) ====
  {
    key: 'PYV-HG-001',
    description: 'Puerta metálica de tambor con pintura electrostática',
    unit: 'pza',
    unitPrice: 4850.00,
    category: 'direct',
    materials: [
      { key: 'MAT-080', description: 'Puerta metálica de tambor 90x210 cm', unit: 'pza', quantity: 1.0, unitCost: 3200.00, amount: 3200.00 },
      { key: 'MAT-081', description: 'Chapa y accesorios', unit: 'jgo', quantity: 1.0, unitCost: 285.00, amount: 285.00 },
      { key: 'MAT-082', description: 'Marco metálico U-100', unit: 'pza', quantity: 1.0, unitCost: 450.00, amount: 450.00 },
    ],
    labor: [
      { key: 'MAN-009', description: 'Herrero oficial', unit: 'hr', quantity: 3.0, unitCost: 105.00, amount: 315.00 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 2.0, unitCost: 52.35, amount: 104.70 },
    ],
    equipment: [
      { key: 'EQ-060', description: 'Soldadora eléctrica 250A', unit: 'hr', quantity: 0.5, unitCost: 125.00, amount: 62.50 },
    ],
  },
  // ==== EXCAVATION (m3) ====
  {
    key: 'TR-HG-001',
    description: 'Excavación a mano en terreno tipo II (semirrocoso)',
    unit: 'm3',
    unitPrice: 385.50,
    category: 'direct',
    materials: [],
    labor: [
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 6.0, unitCost: 52.35, amount: 314.10 },
      { key: 'MAN-010', description: 'Capataz de trabajos', unit: 'hr', quantity: 0.5, unitCost: 125.00, amount: 62.50 },
    ],
    equipment: [
      { key: 'EQ-070', description: 'Herramienta menor (pico, pala, barretón)', unit: 'hr', quantity: 0.6, unitCost: 15.00, amount: 9.00 },
    ],
  },
  {
    key: 'TR-HG-002',
    description: 'Excavación con maquinaria en terreno tipo I',
    unit: 'm3',
    unitPrice: 185.60,
    category: 'direct',
    materials: [
      { key: 'MAT-090', description: 'Diesel para retroexcavadora', unit: 'L', quantity: 3.5, unitCost: 24.50, amount: 85.75 },
    ],
    labor: [
      { key: 'MAN-011', description: 'Operador de maquinaria pesada', unit: 'hr', quantity: 0.8, unitCost: 135.00, amount: 108.00 },
      { key: 'MAN-001', description: 'Peón de construcción', unit: 'hr', quantity: 0.5, unitCost: 52.35, amount: 26.18 },
    ],
    equipment: [
      { key: 'EQ-080', description: 'Retroexcavadora CAT 420E', unit: 'hr', quantity: 0.8, unitCost: 850.00, amount: 680.00 },
    ],
  },
];

/** Get total cost breakdown by category for a list of budget lines */
export function getBreakdownByCategory(lines: { conceptKey: string; quantity: number }[]): Record<string, number> {
  const result: Record<string, number> = { direct: 0, indirect: 0, financing: 0, profit: 0, contingency: 0 };
  for (const line of lines) {
    const concept = CATALOGO_CONCEPTOS.find((c) => c.key === line.conceptKey);
    if (concept) {
      result[concept.category] += concept.unitPrice * line.quantity;
    }
  }
  return result;
}

/** Compute material subtotal for a concept */
export function getMaterialsSubtotal(concept: CatalogElement): number {
  return concept.materials.reduce((sum, m) => sum + m.amount, 0);
}

/** Compute labor subtotal for a concept */
export function getLaborSubtotal(concept: CatalogElement): number {
  return concept.labor.reduce((sum, l) => sum + l.amount, 0);
}

/** Compute equipment subtotal for a concept */
export function getEquipmentSubtotal(concept: CatalogElement): number {
  return concept.equipment.reduce((sum, e) => sum + e.amount, 0);
}

/** Verify unit price = sum of resources */
export function verifyUnitPrice(concept: CatalogElement): { matches: boolean; computed: number; listed: number; diff: number } {
  const computed = getMaterialsSubtotal(concept) + getLaborSubtotal(concept) + getEquipmentSubtotal(concept);
  const listed = concept.unitPrice;
  const diff = Math.abs(computed - listed);
  return { matches: diff < 0.01, computed, listed, diff };
}
