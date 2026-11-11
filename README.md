# PDF Toolbox 📄

Herramienta local rápida, ligera y con una interfaz web limpia y sobria para procesar y optimizar archivos PDF.

## Características
- **Digitalizar Libro / Documento (OCR)**: Convierte fotos de páginas, escaneos o PDFs de solo imagen en un **PDF con texto 100% seleccionable, buscable y copiable** (Searchable PDF).
  - *Soporte multilingüe*: Español (`spa`), Inglés (`eng`) y bilingüe (`spa+eng`).
  - *Lote de imágenes*: Carga múltiple de páginas (JPG, PNG, WEBP, TIFF) con ordenamiento natural automático (`pág 1, pág 2...`) y previsualización de miniaturas.
  - *PDFs escaneados*: Procesa PDFs escaneados extrayendo y dotando de capa tipográfica invisible a cada página.
  - *Mejoras de imagen*: Filtro para limpiar sombras de lomo/doblez y optimizar contraste; detección automática de orientación (rotación de páginas desalineadas).
  - *Doble exportación*: Descarga el PDF con texto seleccionable y también la transcripción íntegra en `.txt`, con botón de copia rápida al portapapeles.
- **Aligerar PDF**: Reduce el tamaño de documentos pesados utilizando Ghostscript y PyMuPDF. Ofrece modos:
  - *Máxima compresión* (~72 dpi)
  - *Equilibrada / Recomendada* (~150 dpi)
  - *Alta calidad* (~300 dpi)
  - *Opción Escala de Grises* (máximo ahorro para documentos escaneados o libros).
- **Dividir / Extraer**: Extrae páginas y rangos específicos (ej. `1-10, 25, 40-50`).
- **Unir PDFs**: Combina dos o más archivos en un único PDF ordenado.
- **Rotar**: Rota páginas a 90°, 180° o 270°.
- **Inspeccionar**: Análisis detallado de metadatos, resolución y dimensiones.
- **Web a PDF (Artículos / Zotero)**: Convierte artículos web y posts de blogs a PDFs limpios con texto vectorial 100% seleccionable.
  - *Modo Artículo Limpio*: Elimina cookies, anuncios y barras laterales, aplicando formato editorial para lectura y subrayado en Zotero.
  - *Metadatos Zotero*: Incrusta automáticamente título, autor, fecha y URL original.
  - *Modo Página Completa*: Captura la página entera respetando sus estilos originales.
- **Acceso Directo Local**: Detecta automáticamente archivos PDF en la carpeta superior (como `tomo25.pdf`) para probar con un solo clic.

## Requisitos y Entorno Conda
El proyecto utiliza un entorno dedicado de Miniconda (`pdf-toolkit` con Python 3.12).
Para ejecutarlo:

```bash
# Desde la carpeta pdf-toolbox
./run.sh
```

Abre tu navegador en la URL mostrada en la terminal (por defecto `http://127.0.0.1:8000`).
