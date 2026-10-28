# FolderExporter

A tiny, **Windows 95/98-inspired** desktop tool for exporting drawing folders from Clip Studio Paint and Photoshop projects as individual images.

**No Python installation is needed** to run the packaged macOS or Windows app.

## Workflow

1. Choose a source `.psd`, `.psb`, or (experimental) `.clip` document.
2. The left side shows **01 File** and **02 Folders Found** in separate classic boxes.
3. Type comma-separated organizational folder keywords (default: `chapter, section`).
4. Folders containing those words are **not** exported as drawings. Their drawing folders are discovered recursively.
5. Select drawing folders; each chapter retains its own output directory.
6. Customize the format, background, output destination and Finder-style names on the right.
7. Click **Export All**, always visible in the fixed bottom bar.

Example:

```text
Clip Studio Project
├── Chapter 3
│   ├── 1
│   ├── 2
│   └── 3
└── Chapter 12
    ├── 1
    └── 2

FolderExporter Exports
├── Chapter 3
│   ├── 1.png
│   ├── 2.png
│   └── 3.png
└── Chapter 12
    ├── 1.png
    └── 2.png
```

The original top-to-bottom layer order is retained. Identically named drawings from different chapters can keep their names.

## Naming like Finder

- **Format:** Name Only, Name and Index, Name and Counter, Name and Date.
- **Add Text:** add a custom string before or after the original folder name.
- **Replace Text:** find a string and replace it in the original folder name.
- Custom prefix/format, starting number, padding, placement, separator and numbering reset per chapter.
- The preview shows the **actual paths** that will be created before export.
- Existing images are never overwritten: a colliding name gets ` - 2`, ` - 3`, etc.

## Export options

PNG, WebP, TIFF and JPEG; scale, JPEG/WebP quality, crop to drawing bounds, optional opaque white background, JPEG matte and choice of destination. Transparent PNG/WebP/TIFF is the default.

## Original files are read-only

Opening PSD/PSB/CLIP only loads and interprets the data. The app does not call source save/write methods, edit source layers or overwrite existing files. Only *new* exports are written into the chosen output location.

**PSD files are recommended.** Direct `.clip` rendering is experimental and may reject folders using masks, advanced blend modes, clipping, vector-only contents or adjustments. Such folders should be exported through PSD. Compare complex exports against Clip Studio.

The standalone build bundles the open-source `psd-tools` and `clipparse` readers. No source file is converted or rewritten.

## Download

In [GitHub Actions](https://github.com/oyayasu/FolderExporter/actions), open the latest **successful** "Build Windows and macOS" run and download the artifact for your architecture.

- **Windows x64:** extract the GitHub ZIP and run `FolderExporter.exe` with the `_internal` folder beside it.
- **Mac Apple Silicon:** extract the ZIP, open the enclosed `.dmg` and drag `FolderExporter.app` into Applications.
- **Mac Intel:** use the Intel artifact instead.

The macOS app isn't signed/notarized. If macOS blocks its first launch, authorize it in System Settings > Privacy & Security.

## Building from source

Development-only: `pip install -r requirements.txt pytest` then `python app.py`. GitHub Actions installs and packages these dependencies for end users.
