import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

pdf = pdfium.PdfDocument("test.pdf")
version = pdf.get_version()  # get the PDF standard version
n_pages = len(pdf)  # get the number of pages in the document
page = pdf[2]  # load a page

bitmap = page.render(
    scale = 1,    # 72dpi resolution
    rotation = 0, # no additional rotation
    # ... further rendering options
)
pil_image = bitmap.to_pil()
pil_image.save("test.png")
#pil_image.show()