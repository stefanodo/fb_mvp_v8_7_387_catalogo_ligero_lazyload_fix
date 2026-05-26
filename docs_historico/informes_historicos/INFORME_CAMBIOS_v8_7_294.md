# INFORME CAMBIOS · System MAC v8_7_294

## Objetivo
Agregar en Recetas una visión mínima de costes indirectos y salarios, con importes editables y conversión automática a porcentaje.

## Cambios aplicados

### 1. Nuevo bloque en ficha de receta
Se añadió el apartado **Costes indirectos y salarios** dentro de la ficha de receta.

El bloque permite cargar importes de referencia para:
- Ventas netas base.
- Alquiler.
- Servicios / gestión.
- Administración / software.
- Publicidad.
- Otros / impuestos operativos.
- Salarios.

### 2. Con IVA / sin IVA
Cada coste indirecto configurable, excepto salarios, tiene selector:
- **sin IVA**: el importe se toma como neto.
- **con IVA**: el sistema lo normaliza a neto antes de calcular el porcentaje.

Los salarios se tratan como coste sin IVA.

### 3. Traducción a porcentaje
El sistema no mete esos importes como coste directo de receta. Los traduce a porcentaje sobre la base de ventas netas indicada:

```text
porcentaje = importe neto / ventas netas base × 100
```

También muestra:
- % alquiler.
- % servicios.
- % administración/software.
- % publicidad.
- % otros.
- % salarios.
- % total estructura.
- carga estimada por ración según precio neto de la receta.

### 4. Persistencia en base de datos
Se añadieron columnas nuevas en `recipes` mediante migración segura en `ensure_columns()`:

- `indirect_sales_base`
- `indirect_rent_amount`
- `indirect_rent_tax_mode`
- `indirect_services_amount`
- `indirect_services_tax_mode`
- `indirect_admin_amount`
- `indirect_admin_tax_mode`
- `indirect_marketing_amount`
- `indirect_marketing_tax_mode`
- `indirect_other_amount`
- `indirect_other_tax_mode`
- `salary_cost_amount`

### 5. Actualización automática en pantalla
Al cambiar cualquier importe, selector IVA/sin IVA, precio manual, food cost objetivo o rendimiento, se recalculan automáticamente los porcentajes y la carga por ración.

## Archivos modificados
- `backend/app/core.py`
- `backend/app/routers/recetas.py`
- `backend/app/templates/partials/recipes_form_main.html`
- `backend/app/static/js/recetas.js`
- `backend/app/static/css/recipes.css`
- `VERSION_BUILD.txt`

## Validaciones realizadas
- Compilación Python de `core.py` y `recetas.py`: OK.
- Importación de `app.main`: OK.
- Render de página Recetas con receta seleccionada: OK.
- POST de actualización de receta con costes indirectos: OK.
- Cálculo comprobado:
  - alquiler 6.050 € con IVA sobre ventas netas 100.000 € = 5,00% neto.
  - servicios 3.000 € sin IVA = 3,00%.
  - salarios 30.000 € = 30,00%.

## No tocado
- OCR.
- Dictado por voz.
- Producciones.
- Pedidos.
- Stock.
- Inventario físico.
- Árbol duplicado ya congelado de la versión anterior.

## Limitación consciente
El sistema usa una normalización fija de IVA indirecto del 21% para los importes marcados como “con IVA”. Si más adelante se quiere máxima precisión fiscal, conviene permitir IVA editable por línea: 0%, 4%, 10%, 21%.
