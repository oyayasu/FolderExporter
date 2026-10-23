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

Abra **Actions → Build Windows and macOS → execução mais recente → Artifacts** e baixe a versão do seu sistema. O build do Windows gera uma pasta com `FolderExporter.exe`; o do macOS gera `FolderExporter.app` num ZIP. No macOS, apps não assinados podem precisar ser autorizados em Ajustes do Sistema > Privacidade e Segurança.

## Limitação

O motor usa `psd-tools` para renderizar grupos PSD. Alguns filtros, máscaras e modos de mesclagem exclusivos do Photoshop/Clip Studio podem não ser reproduzidos perfeitamente. Valide com seu arquivo antes de excluir qualquer exportação original. A entrada direta `.clip` ainda não é suportada.

## Desenvolvimento

Somente para quem quiser desenvolver: `pip install -r requirements.txt` e `python app.py`. O GitHub Actions instala as dependências automaticamente durante a compilação.