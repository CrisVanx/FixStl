#!/usr/bin/env python3

'''
# 1. Crear el entorno virtual en la carpeta donde está tu script
python3 -m venv venv

# 2. Activarlo
source venv/bin/activate

# 4. Correr el script
python3 Flix.py modelo.stl


source venv/bin/activate
'''



import sys
import os
import argparse
import time

# ── Verificar dependencias ──────────────────────────────────────────────────
def check_deps():
    missing = []
    try:
        import trimesh
    except ImportError:
        missing.append("trimesh")
    try:
        import pymeshfix
    except ImportError:
        missing.append("pymeshfix")
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    if missing:
        print(" Faltan dependencias. Instálalas con:")
        print(f"    pip install {' '.join(missing)}")
        sys.exit(1)

check_deps()

import numpy as np
import trimesh
import pymeshfix

# ── Colores ANSI ───────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✔{RESET}  {msg}")
def warn(msg):  print(f"  {YELLOW}⚠{RESET}  {msg}")
def err(msg):   print(f"  {RED}✘{RESET}  {msg}")
def info(msg):  print(f"  {CYAN}→{RESET}  {msg}")
def section(title):
    print(f"\n{BOLD}{title}{RESET}")
    print("  " + "─" * 50)


# ── Diagnóstico ────────────────────────────────────────────────────────────
def diagnose(mesh: trimesh.Trimesh) -> dict:
    """Analiza la malla y retorna un diccionario con los problemas encontrados."""
    issues = {}

    # Vértices y caras básicas
    issues["vertices"]          = len(mesh.vertices)
    issues["faces"]             = len(mesh.faces)

    # Vértices duplicados
    unique, counts              = np.unique(mesh.vertices, axis=0, return_counts=True)
    issues["duplicate_verts"]   = int(np.sum(counts > 1))

    # Vértices no referenciados
    referenced                  = np.unique(mesh.faces)
    issues["unreferenced_verts"]= len(mesh.vertices) - len(referenced)

    # Caras degeneradas (área ≈ 0)
    areas                       = mesh.area_faces
    issues["degenerate_faces"]  = int(np.sum(areas < 1e-12))

    # Aristas de borde abierto (open edges → huecos)
    # Una arista es "abierta" si aparece solo 1 vez (no compartida por 2 caras)
    edge_counts = np.bincount(
        mesh.edges_sorted[:, 0] * (len(mesh.vertices) + 1) + mesh.edges_sorted[:, 1]
        if len(mesh.edges_sorted) > 0 else np.array([], dtype=int)
    )
    # Contar usando edges_unique y face adjacency
    from collections import Counter
    edge_tuples = [tuple(e) for e in mesh.edges_sorted]
    edge_freq   = Counter(edge_tuples)
    issues["open_edges"] = sum(1 for v in edge_freq.values() if v == 1)

    # Caras no-manifold (aristas compartidas por > 2 caras)
    edges_face_count            = np.bincount(mesh.edges_sorted.flatten(),
                                              minlength=len(mesh.vertices))
    # trimesh provee is_watertight y is_volume directamente
    issues["is_watertight"]     = bool(mesh.is_watertight)
    issues["is_volume"]         = bool(mesh.is_volume)

    # Componentes conectados
    components                  = mesh.split(only_watertight=False)
    issues["components"]        = len(components)

    # Normales inconsistentes (trimesh las unifica; detectamos si hubo inversión)
    issues["winding_consistent"]= bool(mesh.is_winding_consistent)

    return issues


def print_diagnosis(issues: dict):
    section("📋  DIAGNÓSTICO INICIAL")

    info(f"Vértices  : {issues['vertices']:,}")
    info(f"Caras     : {issues['faces']:,}")
    info(f"Componentes separados: {issues['components']}")

    if issues["duplicate_verts"] > 0:
        warn(f"Vértices duplicados   : {issues['duplicate_verts']:,}")
    else:
        ok("Sin vértices duplicados")

    if issues["unreferenced_verts"] > 0:
        warn(f"Vértices no referenciados: {issues['unreferenced_verts']:,}")
    else:
        ok("Sin vértices no referenciados")

    if issues["degenerate_faces"] > 0:
        warn(f"Caras degeneradas (área≈0): {issues['degenerate_faces']:,}")
    else:
        ok("Sin caras degeneradas")

    if issues["open_edges"] > 0:
        err(f"Aristas abiertas (huecos)  : {issues['open_edges']:,}")
    else:
        ok("Malla cerrada (sin huecos detectados por trimesh)")

    if not issues["winding_consistent"]:
        warn("Orientación de normales inconsistente")
    else:
        ok("Normales orientadas consistentemente")

    if issues["is_watertight"]:
        ok("La malla YA es watertight (cerrada y válida)")
    else:
        err("La malla NO es watertight → requiere reparación")


# ── Reparación con trimesh ─────────────────────────────────────────────────
def repair_trimesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Aplica las reparaciones básicas de trimesh."""

    # 1. Eliminar vértices duplicados y no referenciados
    mesh.merge_vertices()
    mesh.remove_unreferenced_vertices()

    # 2. Eliminar caras degeneradas
    mask_degen = mesh.nondegenerate_faces()
    mesh.update_faces(mask_degen)

    # 3. Eliminar caras duplicadas
    mask_unique = trimesh.grouping.unique_rows(np.sort(mesh.faces, axis=1))[1]
    mesh.update_faces(mask_unique)

    # 4. Unificar orientación de normales
    trimesh.repair.fix_normals(mesh)

    # 5. Intentar cerrar huecos pequeños
    trimesh.repair.fill_holes(mesh)

    return mesh


# ── Reparación con pymeshfix ───────────────────────────────────────────────
def repair_pymeshfix(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Usa pymeshfix para reparar huecos y problemas no-manifold más complejos."""
    tin = pymeshfix.MeshFix(mesh.vertices, mesh.faces)
    try:
        tin.repair(verbose=False)
    except TypeError:
        tin.repair()
    repaired = trimesh.Trimesh(vertices=tin.points, faces=tin.faces, process=False)
    return repaired


# ── Comparar antes/después ─────────────────────────────────────────────────
def print_summary(before: dict, after: dict, elapsed: float):
    section("📊  RESUMEN DE REPARACIÓN")

    def delta(key, label, invert=False):
        b, a = before[key], after[key]
        diff = a - b
        if diff == 0:
            ok(f"{label}: {a:,}  (sin cambio)")
        elif (diff < 0) ^ invert:
            ok(f"{label}: {b:,} → {a:,}  ({abs(diff):,} {'eliminados' if diff < 0 else 'añadidos'})")
        else:
            warn(f"{label}: {b:,} → {a:,}  ({abs(diff):,} {'eliminados' if diff < 0 else 'añadidos'})")

    delta("vertices",           "Vértices")
    delta("faces",              "Caras")
    delta("duplicate_verts",    "Vértices duplicados")
    delta("unreferenced_verts", "Vértices no referenciados")
    delta("degenerate_faces",   "Caras degeneradas")
    delta("open_edges",         "Aristas abiertas (huecos)")

    print()
    if after["is_watertight"]:
        ok(f"{GREEN}{BOLD}Malla watertight: ✔  La reparación fue exitosa{RESET}")
    else:
        warn("Malla todavía no es completamente watertight")
        warn("Considera revisar manualmente con Blender o Meshmixer")

    if after["winding_consistent"]:
        ok("Normales consistentes: ✔")

    print(f"\n  ⏱  Tiempo total: {elapsed:.2f}s")


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Repara archivos STL localmente (equivalente a formware online STL repair)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python stl_repair.py modelo.stl
  python stl_repair.py modelo.stl --output modelo_fixed.stl
  python stl_repair.py modelo.stl --only-trimesh
        """
    )
    parser.add_argument("input",         help="Archivo STL de entrada (.stl)")
    parser.add_argument("--output", "-o",help="Archivo STL de salida (default: <nombre>_fixed.stl)")
    parser.add_argument("--only-trimesh",action="store_true",
                        help="Usar solo trimesh (más rápido, menos agresivo)")
    args = parser.parse_args()

    # Validar entrada
    if not os.path.isfile(args.input):
        print(f"{RED}Error: No se encontró el archivo '{args.input}'{RESET}")
        sys.exit(1)

    # Nombre de salida
    if args.output:
        output_path = args.output
    else:
        base, ext = os.path.splitext(args.input)
        output_path = f"{base}_fixed{ext}"

    print(f"\n{BOLD}🔧  STL Repair Tool{RESET}")
    print(f"  Entrada : {args.input}")
    print(f"  Salida  : {output_path}")

    start = time.time()

    # Cargar
    section("CARGANDO ARCHIVO")
    try:
        mesh = trimesh.load(args.input, force="mesh")
        ok(f"Archivo cargado correctamente")
    except Exception as e:
        err(f"No se pudo cargar el STL: {e}")
        sys.exit(1)

    if not isinstance(mesh, trimesh.Trimesh):
        # Si viene como Scene, tomar la primera malla
        if isinstance(mesh, trimesh.Scene) and len(mesh.geometry) > 0:
            mesh = list(mesh.geometry.values())[0]
            warn("El archivo contenía una escena; se usó la primera malla")
        else:
            err("No se pudo interpretar el archivo como una malla triangular")
            sys.exit(1)

    # Diagnóstico inicial
    before = diagnose(mesh)
    print_diagnosis(before)

    if before["is_watertight"] and before["duplicate_verts"] == 0 \
       and before["degenerate_faces"] == 0:
        print(f"\n{GREEN}{BOLD}  ✔  El archivo no necesita reparación.{RESET}\n")
        sys.exit(0)

    # Reparación
    section("🛠   REPARANDO")

    info("Paso 1/2: Reparación básica (trimesh)...")
    mesh = repair_trimesh(mesh)
    ok("Completado")

    if not args.only_trimesh:
        info("Paso 2/2: Reparación avanzada de huecos (pymeshfix)...")
        try:
            mesh = repair_pymeshfix(mesh)
            ok("Completado")
        except Exception as e:
            warn(f"pymeshfix falló ({e}), se usa resultado de trimesh")

    # Diagnóstico final
    after = diagnose(mesh)

    elapsed = time.time() - start
    print_summary(before, after, elapsed)

    # Exportar
    section("EXPORTANDO")
    try:
        mesh.export(output_path)
        ok(f"Guardado en: {output_path}")
    except Exception as e:
        err(f"Error al guardar: {e}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()