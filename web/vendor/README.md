# Vendored libraries

These files are copied verbatim from npm so the page works as a plain static
site with no runtime dependency on any CDN, and no network request when a
label is checked.

| Path | Package | Purpose |
| --- | --- | --- |
| `tesseract/tesseract.min.js` | `tesseract.js` | Browser API |
| `tesseract/worker.min.js` | `tesseract.js` | Web Worker that drives OCR |
| `core/tesseract-core-simd-lstm.wasm.js` | `tesseract.js-core` | OCR engine, WebAssembly SIMD build |
| `core/tesseract-core-lstm.wasm.js` | `tesseract.js-core` | Same engine for browsers without SIMD |
| `lang/eng.traineddata.gz` | `@tesseract.js-data/eng` | English model (`4.0.0_best_int`) |

Tesseract and tesseract.js are Apache-2.0 licensed. The training data is
Apache-2.0 from the tessdata project.

Only these four files are actually requested at runtime; the package also
ships bare `.wasm` files and separate loaders that this configuration does
not use, and they are deliberately not vendored.

To refresh them:

    npm install tesseract.js@6 tesseract.js-core@6 @tesseract.js-data/eng
    # then copy the files listed above out of node_modules/
