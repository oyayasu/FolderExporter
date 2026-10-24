# FolderExporter

Exporta cada pasta principal de um PSD/PSB como imagem individual, preservando a transparência e sem modificar o projeto.

**Windows e macOS:** a aba [Actions](https://github.com/oyayasu/FolderExporter/actions) gera os aplicativos independentes. Quem usa o aplicativo **não precisa instalar Python**.

## Recursos

- Cada grupo principal vira um arquivo independente, incluindo grupos ocultos.
- Formatos: PNG, WebP, TIFF e JPEG.
- Nomes originais, numeração, ou combinação dos dois.
- Nomes repetidos recebem ` - 2`, ` - 3`, etc.; arquivos anteriores nunca são sobrescritos.
- Exportar na pasta original, em subpasta própria ou em destino escolhido.
- Tela completa ou recorte do conteúdo, escala, qualidade e fundo de JPEG.
- Seleção de grupos, progresso e cancelamento.

## Baixar

Abra **Actions → Build Windows and macOS → última execução verde → Artifacts**. As versões do programa **não exigem instalar Python**.

### Windows 10/11
1. Baixe `FolderExporter-Windows-x64` (um único arquivo ZIP do GitHub).
2. Extraia o ZIP **completo** para uma pasta.
3. Execute `FolderExporter.exe` e mantenha a pasta `_internal` ao lado dele. Não execute o EXE de dentro do ZIP.

### macOS Intel ou Apple Silicon
1. Baixe o artifact de arquitetura correspondente. O ZIP do GitHub contém um arquivo `.dmg`, e **não outro ZIP**.
2. Extraia o ZIP, abra o `.dmg` e copie `FolderExporter.app` para Aplicativos.
3. O aplicativo ainda não é assinado/notarizado. Caso o macOS bloqueie a abertura, confira **Ajustes do Sistema → Privacidade e Segurança**, em vez de desativar o Gatekeeper globalmente.

### Importante
- Arquivos existentes não são substituídos; nomes repetidos ganham sufixos ` - 2`, ` - 3` etc.
- O GitHub testa o núcleo de exportação e verifica a inicialização da janela no Windows.
- Ainda é necessário validar o resultado com PSDs reais exportados pelo Clip Studio.

## Limitação

O motor usa `psd-tools` para renderizar grupos PSD. Alguns filtros, máscaras e modos de mesclagem exclusivos do Photoshop/Clip Studio podem não ser reproduzidos perfeitamente. Valide com seu arquivo antes de excluir qualquer exportação original. A entrada direta `.clip` ainda não é suportada.

## Desenvolvimento

Somente para quem quiser desenvolver: `pip install -r requirements.txt` e `python app.py`. O GitHub Actions instala as dependências automaticamente durante a compilação.