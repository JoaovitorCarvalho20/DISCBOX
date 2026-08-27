# DISCBOX

Baixador de músicas do Spotify: você cola a URL de uma faixa, álbum ou playlist, o DISCBOX lê os metadados (título, artista, álbum, capa) direto da Spotify, encontra o áudio correspondente no YouTube, baixa, converte e grava tudo — tags e capa incluídas — no formato que você escolher.

Não precisa de conta de desenvolvedor da Spotify, nem de Client ID/Secret, nem de login. Também não usa nenhuma API paga ou mirror de terceiros — só a própria página pública que o player incorporado da Spotify usa.

## Baixar e usar (sem instalar nada)

Pegue a versão mais recente na página de **[Releases](https://github.com/JoaovitorCarvalho20/DISCBOX/releases)** — baixe o executável do seu sistema (`DISCBOX.exe` no Windows, `DISCBOX.app` no macOS, ou `DISCBOX` no Linux) e abra direto. Não precisa instalar Python, e o FFmpeg já vem embutido dentro do app.

Se em vez disso você tem o código-fonte e quer gerar esse executável você mesmo, veja [Gerando o executável](#gerando-o-executável) mais abaixo.

## Como funciona

1. **Metadados** (`spotify_client.py`) — a URL é lida na página de embed pública da Spotify (`open.spotify.com/embed/...`), que carrega um bloco JSON com título, artistas, álbum, capa e duração de cada faixa. Nenhuma autenticação é necessária.
   - Playlists com mais de ~100 faixas (limite da página de embed) são completadas via *spclient*, a API interna que o player da Spotify usa para tocar a playlist inteira — usando um token anônimo que a própria página de embed já carrega.
2. **Busca no YouTube** (`youtube_search.py`) — para cada faixa, busca os 5 primeiros resultados no YouTube via `yt-dlp`, filtra por título e artista (rejeitando remixes/covers com nome parecido) e escolhe o de duração mais próxima da faixa original. Também prioriza a versão de estúdio quando o título do YouTube indica "ao vivo"/"acústico".
3. **Download** (`downloader.py`) — baixa o áudio via `yt-dlp` e converte com FFmpeg. Se o YouTube bloquear o download com um desafio anti-bot, tenta de novo automaticamente com clientes alternativos (Android/iOS/TV) antes de desistir.
4. **Tags e capa** (`metadata_handler.py`) — grava título, artista, álbum, data e a capa do álbum embutida no arquivo, no formato correto pra cada container (ID3 pra mp3, átomos iTunes pra m4a, Vorbis comments pra flac).
5. **Organização** (`organizer.py`) — álbuns e playlists viram uma subpasta (nome sanitizado pra ser seguro em Windows/Mac/Linux); faixas avulsas vão direto pra pasta de downloads.
6. **Duplicatas** (`duplicate_checker.py`) — se o arquivo de destino já existe, a faixa é pulada em vez de baixada de novo.

## Rodando a partir do código-fonte

Precisa de:

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/) instalado e no PATH (necessário pra converter o áudio)
- Windows, macOS ou Linux

```bash
# 1. Crie e ative um ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Copie o template de configuração (opcional — os padrões já funcionam)
cp .env.example .env
```

Nenhuma credencial é necessária no `.env` — as variáveis ali são só preferências (pasta de download, formato, qualidade padrão).

Se não tiver o FFmpeg instalado:

```bash
# Windows (via winget)
winget install --id Gyan.FFmpeg -e

# macOS (via Homebrew)
brew install ffmpeg

# Linux (Debian/Ubuntu)
sudo apt install ffmpeg
```

### Interface gráfica

```bash
python main.py --gui
```

Fluxo: cole a URL → **Buscar** (mostra capa e lista de faixas, sem baixar nada) → confira/ajuste formato, qualidade e pasta na aba **Configurações** → **Baixar**. Dá pra cancelar no meio (termina a faixa atual e para) e, se alguma faixa falhar, um botão **Ver falhas** aparece com a lista.

### Linha de comando

```bash
python main.py "<url-da-spotify>" [--format mp3] [--quality 320] [--out PASTA]
```

Exemplos:

```bash
python main.py "https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3"
python main.py "https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv" --format flac
python main.py "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" --out "D:\Músicas"
```

Aceita URLs de faixa, álbum ou playlist — canônicas (`open.spotify.com/...`), com prefixo de idioma (`/intl-pt/...`) ou no formato URI (`spotify:track:...`).

A CLI só existe rodando a partir do código-fonte — o executável empacotado abre direto na GUI.

## Configuração

Variáveis opcionais em `.env` (veja `.env.example`):

| Variável         | Padrão                                                    | Descrição                                                                          |
| ----------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `DOWNLOAD_DIR`  | `./downloads` (fonte) / `~/Music/DISCBOX` (empacotado) | Pasta onde as músicas são salvas                                                   |
| `AUDIO_FORMAT`  | `mp3`                                                    | Formato de saída:`mp3`, `m4a`, `opus`, `flac`, `wav`                      |
| `AUDIO_QUALITY` | `320`                                                    | Qualidade em kbps (`128`/`192`/`256`/`320`), vale só pra formatos com perda |

Na GUI, a última pasta/formato/qualidade escolhidos ficam salvos e voltam pré-selecionados na próxima vez que o app abrir — na pasta do projeto rodando a partir do código-fonte, ou na pasta de configuração padrão do sistema (`%APPDATA%\DISCBOX` no Windows, `~/Library/Application Support/DISCBOX` no macOS, `~/.config/DISCBOX` no Linux) quando empacotado.

## Gerando o executável

O build usa [PyInstaller](https://pyinstaller.org/) pra empacotar o app + Python + FFmpeg num único executável. **PyInstaller não faz cross-compile** — o build de cada sistema só pode ser gerado rodando naquele sistema.

### Automático (GitHub Actions)

O workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) builda os três sistemas em paralelo — um runner Windows, um macOS e um Linux do próprio GitHub Actions — e publica os três instaladores direto na aba **[Releases](https://github.com/JoaovitorCarvalho20/DISCBOX/releases)**. É assim que os builds oferecidos pra download são gerados; não depende de ninguém ter uma máquina Windows/Mac/Linux pra rodar os scripts manuais abaixo.

Pra publicar uma versão nova: dê push numa tag `vX.Y.Z`, por exemplo:

```bash
git tag v1.0.0
git push origin v1.0.0
```

O workflow também pode ser disparado manualmente pela aba **Actions → Build e Release → Run workflow** (builda os três, mas sem criar/atualizar um release — útil só pra testar se o build passa).

### Manual (rodando localmente)

```bash
# Windows (PowerShell)
.\scripts\build_windows.ps1

# macOS
./scripts/build_macos.sh

# Linux
./scripts/build_linux.sh
```

Cada script cria/usa o `.venv`, instala as dependências de build (`requirements-build.txt`), embute o FFmpeg do sistema se ele já estiver instalado (senão o build sai sem ele, e quem for usar precisa instalar separadamente) e roda `pyinstaller discbox.spec`. O resultado sai em `dist/`:

- Windows: `dist\DISCBOX.exe`
- macOS: `dist/DISCBOX.app`
- Linux: `dist/DISCBOX`

## Estrutura do projeto

```
music_archiver/
├── main.py                 # Ponto de entrada da CLI (rodando a partir do código-fonte)
├── discbox_app.py           # Ponto de entrada do executável empacotado (sempre abre a GUI)
├── gui.py                    # Interface gráfica (PyQt6)
├── config.py                  # Configurações e persistência de preferências
├── spotify_client.py          # Leitura de metadados da Spotify (sem API key)
├── youtube_search.py          # Busca e seleção do melhor vídeo no YouTube
├── downloader.py                # Download + conversão de áudio via yt-dlp/FFmpeg
├── metadata_handler.py          # Gravação de tags ID3/iTunes/Vorbis + capa
├── organizer.py                  # Nomes de arquivo/pasta seguros
├── duplicate_checker.py          # Evita baixar a mesma faixa duas vezes
├── assets/
│   ├── icon.svg                    # Ícone do app
│   ├── icon.png
│   └── icon.ico                    # Ícone do executável Windows
├── scripts/
│   ├── build_windows.ps1
│   ├── build_macos.sh
│   └── build_linux.sh
├── discbox.spec               # Config do PyInstaller
├── requirements.txt            # Dependências pra rodar
├── requirements-build.txt      # + dependências pra gerar o executável
├── .env.example
└── downloads/                   # Pasta padrão de saída (código-fonte; criada automaticamente)
```

## Limitações conhecidas

- Só funciona com conteúdo **público** da Spotify — não acessa playlists privadas nem sua biblioteca pessoal (curtidas, "Descobertas da Semana", etc.), já que não há login.
- A qualidade do áudio depende do que está disponível no YouTube — não é um rip direto da Spotify.
- Faixas muito obscuras ou regravações incomuns podem não ter uma correspondência confiável no YouTube; nesses casos a faixa é marcada como "não encontrada" em vez de baixar algo errado.
- O executável com FFmpeg embutido fica pesado (~140 MB no Windows) — é o preço de não exigir uma instalação separada.

## Aviso

Este projeto foi feito para fins de estudo e uso pessoal. Baixar conteúdo protegido por direitos autorais sem autorização pode violar os termos de uso da Spotify e do YouTube, além da legislação de direitos autorais aplicável. Use com responsabilidade, preferencialmente apenas para conteúdo que você já tem o direito de baixar (ex: suas próprias composições, música de domínio público, ou licenças que permitam).
