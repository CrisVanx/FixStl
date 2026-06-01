# FixStl

Herramienta simple en Python para diagnosticar y reparar archivos STL.

## Descripción

`Flix.py` carga un STL, analiza su geometría, aplica reparaciones con `trimesh` y `pymeshfix`, y exporta una versión corregida.

## Requisitos

- Python 3
- numpy
- trimesh
- pymeshfix

## Instalación

```bash
cd /Users/cristiangonzalez/Documents/Dev
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python3 Flix.py modelo.stl
```

Salida por defecto:

```bash
modelo_fixed.stl
```

Opciones:

- `-o, --output` : nombre del archivo STL de salida
- `--only-trimesh` : usa solo la reparación básica de `trimesh`

Ejemplo:

```bash
python3 Flix.py modelo.stl --output modelo_reparado.stl
```

## Notas

- Los archivos `.stl` grandes se excluyen del repositorio mediante `.gitignore`.
- Si `pymeshfix` falla, el script intenta guardar el resultado de `trimesh`.
