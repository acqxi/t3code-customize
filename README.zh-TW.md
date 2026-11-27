# t3code-customize

[English](README.md) | [繁體中文](README.zh-TW.md)

在 T3 Code 輸入框下方顯示 5 小時與每週用量、脈絡使用量，以及每秒產生的 token 數。

非官方專案，與 T3 Tools 無關。支援 Linux（AppImage）、macOS 與 Windows 上的 T3 Code（Nightly、Beta 或 Release），包括後端在 WSL 執行的 Windows 桌面版。

## 功能

- **用量計量條**：5 小時與每週額度的使用情況，資料來自 T3 已經向模型供應商取得的額度資訊。所有回報額度的模型供應商都會顯示，前面加上各自的圖示與強調色，目前對話串的排在最前面；也可以設定成只顯示目前的模型供應商。
- **脈絡使用量**：目前對話串用掉的脈絡。滑鼠移上去可以看到脈絡視窗大小、自動壓縮門檻，以及「立即壓縮」按鈕。
- **每秒 token 數**：上一則回覆的產生速度。滑鼠移上去可以看到該輪耗時與 token 明細。
- **快取命中率**：上一輪的快取命中率。
- **效能指標**：首個 token 時間、首段回答時間，即時、平均與峰值 tokens/s，token 與快取用量，工具耗時與整輪耗時，以及每一輪的模型供應商、模型、推理強度與速度模式。可以顯示在每則回覆下方、輸入框下方（本輪與上一輪，排成一行）、Thread details 側欄，或任意組合。估計值標示 `≈`，無法取得的值顯示 `—`；有哪些指標取決於模型供應商。Codex、Claude Code 與 Antigravity 等 ACP 代理都依串流內容計時。效能明細可以在「最後一輪」、「整個對話串」與「各模型」之間切換；Usage 儀表板的模型明細也會加上各模型的 tok/s、TTFT 與 TTFA。定義見 [docs/performance-metrics.md](docs/performance-metrics.md)。
- **訂閱切換**：同一個模型有多個已登入的訂閱可用時，若目前的訂閱照這個速度會在 5 小時或每週額度重置前用完，會出現像 **Opus 5.5 on Personal →** 的標籤，點一下就把對話串切到額度最充裕的那個訂閱上的同一個模型。每週額度將在一天內重置、卻還剩很多的訂閱也會提示。滑鼠移上去可以看到判斷依據。
- **WSL 主機橋接**（使用 WSL 後端的 Windows Desktop）：WSL 中的代理可以透過 T3 原生的 Linked environments，把需要 Windows 的工作（瀏覽器、Computer Use、GUI 程式或 PowerShell）交給同一台電腦上的 Windows 後端。Desktop 經由 `wsl.exe` 的 stdio 轉送，Windows 後端不必開放網路存取。可在 Environments 地圖上的 **Host bridge** 連線，或在 **Settings > Connections > Local host bridge** 開啟。說明見 [docs/wsl-host-bridge.md](docs/wsl-host-bridge.md)。

客製版沿用官方 App 的原生相依套件與 T3 Connect 公開設定。Windows 簽章變動與平台限制說明如下。

## 支援的 T3 Code 版本

每個支援的版本在 `patches/<版本>/` 都有自己的 patch 組。工具會讀取已安裝 T3 Code 對應的 upstream commit，自動選用相符的那一組，所以版本不同的機器可以用同一份程式碼建置。

| T3 Code | Patch 組 | 狀態 |
| --- | --- | --- |
| 0.1.13 | `patches/0.1.13` | 移植中 |
| 0.1.12 | `patches/0.1.12` | 支援 |

沒有專屬 patch 組的版本，會從最接近的較舊版本那組開始建置。如果那些 patch 套不上去，請見〈nightly 更新讓 patch 失效時〉；移植完成後會另存成新的一組，舊的那幾組都會保留。

## 安裝

請先安裝 T3 Code（Nightly、Beta 或 Release）。需要 Git、Python **3.10 以上**、網路連線，以及約 **6 GB** 的可用空間。工具會使用 upstream 在 `engines.node` 指定的 Node 版本；如果系統上的 Node 版本不同，會另外下載一份經過校驗和驗證的私用版本。第一次建置約需 5 到 15 分鐘，視電腦效能而定。

### Windows（PowerShell）

安裝 Git for Windows 與 Python，並確認 `git` 和 `python.exe` 在 PATH 中。複製本儲存庫後直接用 Python 執行，不需要 Git Bash，也不需要系統管理員權限：

```powershell
git clone https://github.com/acqxi/t3code-customize.git
cd t3code-customize
python .\t3code-customize build
```

如果安裝在非預設位置，請傳入**已安裝的執行檔**，不是 NSIS 安裝程式：

```powershell
python .\t3code-customize build --app 'C:\Apps\T3 Code\T3 Code (Nightly).exe'
```

也可以執行儲存庫裡的 `install.ps1`，它會把本儲存庫複製到工具的私用資料夾並進行建置。用 `-App` 指定執行檔，用 `-Branch` 測試功能分支。它不會更改執行原則。

### 後端在 WSL 執行的 Windows 桌面版（Windows 端不需要 Python、Git 或 Node）

如果你的 Windows 版 T3 Code 後端在 WSL 中執行，請**在 WSL 裡**執行工具，並確認可以呼叫 Windows 互通功能（`powershell.exe`）。JavaScript 與 Linux runtime 在 WSL 中建置；檔案複製、雜湊計算、執行檔的完整性資源與「開始」功能表捷徑則透過 Windows PowerShell 處理：

```sh
git clone https://github.com/acqxi/t3code-customize.git
cd t3code-customize
python3 ./t3code-customize build --target windows
```

工具會在 Windows 的 `%LOCALAPPDATA%\Programs` 底下尋找安裝位置（其他位置請傳入 `--app '/mnt/c/.../T3 Code (Beta).exe'`）。WSL 需要 `git`、`python3` 與網路連線，且必須是 x64。建置時會把 App 複製到 `%LOCALAPPDATA%\t3code-customize\builds`，用同一組 patch 重新產生 `resources/wsl-runtime.tar.gz` 與它的 `.sha256`，並在「開始」功能表加入 **T3 Code (Customized)**。已安裝的 App 和它的 WSL runtime 都不會被修改。客製版第一次啟動時，會把自己的 runtime 安裝到獨立的 `~/.t3/wsl-runtime/sha256-…` 資料夾，跟原版的並存。

兩個 App 共用同一份 T3 設定檔（帳號、設定、專案、對話串），所以開啟客製版前請先完全結束原版。`t3code-customize check` 會以唯讀方式回報目前發行版中執行的 runtime、專案與對話串數量，以及每個模型供應商最近完成的一輪；切換前後各執行一次即可比對。

### Linux 與 macOS

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/acqxi/t3code-customize/main/install.sh)"
```

也可以複製本儲存庫後執行 `python3 ./t3code-customize build`。放在 `~/Applications`、`~/Downloads` 及其他標準搜尋資料夾的 AppImage 會自動找到。其他路徑請傳入 `--app /path/to/T3-Code.AppImage`。舊的 `--appimage` 參數仍可使用。

### 啟用統計

建置成功後，**完全結束 T3 Code**。從 Windows「開始」功能表、Linux 應用程式選單或 macOS 的 Spotlight 開啟 **T3 Code (Customized)**，然後開啟 **Settings > Appearance > Stats for nerds**。

客製版開啟後是一般的 T3 Code 主畫面，不會跳出另外的設定精靈。找不到開關的話，請自行打開 Settings 搜尋 **Stats for nerds**。這個開關預設是關閉的。開啟後，統計會顯示在輸入框下方與每則回覆下方；能顯示哪些數值，取決於模型供應商與對話內容。同一個設定區塊裡，每個指標和每個顯示位置都有各自的開關。客製版的視窗標題結尾會加上「(Customized)」，方便跟原版區分。

**Settings > About > Restart** 可以重新載入視窗、重新啟動 T3 Code（會開啟最新的客製版建置），或在後端卡住時強制重啟。WSL runtime 安裝與啟動期間，設定裡的 WSL backend 那一列與 Environments 地圖上的卡片會顯示目前進行到哪一步。

指令包裝程式在 Linux 位於 `~/.local/bin`，在 Windows 位於 `%LOCALAPPDATA%\t3code-customize\bin`。如果它不在 PATH 中，請把該資料夾加入 PATH，或在儲存庫資料夾中執行 `python t3code-customize <指令>`（Linux 用 `python3`）。

macOS 請從 Spotlight、Launchpad 或 `~/Applications` 開啟 **T3 Code (Customized)**。設定方式、日常使用，以及為什麼是把 patch 載入你的 App 而不是重新建置，請見 [macOS 說明](docs/macos.md)。工具會在 `/Applications` 與 `~/Applications` 尋找 `T3 Code (Nightly).app`；其他位置請用 `--app "/path/to/T3 Code (Nightly).app"` 指定一次。

## 每次 T3 Code 更新後

```sh
t3code-customize
```

先更新**官方 App**，再執行工具。它會抓取最新的 patch，針對已安裝的版本重新建置，並告訴你何時重新開啟。在你執行之前，啟動器會改開原版 T3 Code。Windows 客製版已關閉自動更新，請從原本的啟動入口更新原版。

## nightly 更新讓 patch 失效時

upstream 變動很快，有時 nightly 會改到 patch 動到的程式碼。這時可以：

- 如果有安裝 Claude Code 或 Codex，工具會當場提議讓它們幫你移植 patch。
- 或等本儲存庫跟上之後，再執行一次 `t3code-customize`。
- 或請任何 coding agent 依照 [AGENTS.md](AGENTS.md) 處理本儲存庫。

這段期間，你現在的 T3 Code 都能照常使用。

## 運作方式

T3 Code 是開放原始碼軟體（MIT）。本儲存庫包含十二個 patch 與一支腳本。腳本會：

1. 讀取已安裝的 App：它對應的 upstream commit，以及 T3 Connect 需要的公開設定，
2. 把 patch 套用到該 commit 並執行測試，
3. 重新建置 web、伺服器與桌面版的 JavaScript，
4. 在 Linux 與 Windows 上，把建置結果覆蓋到 App 的副本，並逐位元組檢查封存檔中沒變動的項目，
5. 在 Windows 上，更新副本中 Electron 內嵌的封存檔完整性中繼資料，
6. 在 WSL 中為 Windows 建置時，同時重新產生 WSL runtime 封存檔，並保留其中的原生檔案。

有獨立 `server.asar` 的 Windows 版，兩個封存檔都會套用 patch。Linux 使用合併的 `app.asar`。原生函式庫與未封裝的檔案都從已安裝的 App 複製，不會重新編譯替代的二進位檔。

macOS 上不會複製也不會重新簽署，所以 App 會保留簽章、鑰匙圈存取權、密碼金鑰與自動更新。啟動器會用啟動掛鉤開啟你自己的 `T3 Code (Nightly).app`，在任何 App 程式碼執行前載入重新建置的套件，再關閉掛鉤。用其他方式開啟 T3 Code 就是原版。

所有作業都在你的電腦上進行。建置不會修改已安裝的 App 或你的 T3 資料。客製版跟原版使用同一份 T3 設定檔，切換前請先結束原版。

## 指令

```text
t3code-customize             更新 patch，並針對已安裝的 T3 Code 建置
t3code-customize status      顯示下次啟動會開哪個版本
t3code-customize check       唯讀：執行中的 runtime、資料數量、各模型供應商最近的統計
t3code-customize off | on    在原版與客製版之間切換
t3code-customize uninstall   移除工具、啟動器、建置結果與快取
```

## 注意事項

- **回報問題**：向 T3 Code 回報任何問題前，請先執行 `t3code-customize off`，重新開啟並確認原版也會發生。客製功能的問題請回報到這裡。
- **macOS**：從啟動器開啟 T3 Code 時才會套用客製功能。如果 T3 Code 已經在執行，啟動器只會把它帶到前景。這依賴 T3 Code 允許啟動掛鉤（`--inspect-brk`）；如果某個版本關閉了這個功能，建置會停下來並說明原因。
- **Windows 簽章**：更新內嵌封存檔的雜湊值會改動副本的執行檔，因此它不再有官方的 Authenticode 簽章。這是本機的客製副本，不是有簽章、可散佈的安裝程式。
- **Windows WSL 環境**：在 WSL 中建置（`--target windows`）時，Windows 原生伺服器與內嵌的 WSL runtime 都會套用 patch。用 Windows 的 Python 建置時，只會修改原生伺服器，WSL runtime 維持原版（Windows 上無法建置 Linux 單一執行檔）。
- **處理器架構**：私用 Node 下載支援 x64 與 arm64。請在與已安裝 App 相同的架構與平台上建置；唯一的例外是 Windows 桌面版也可以在 WSL 中建置。
- **Linux 與 macOS 的檔案位置**：資料與建置結果在 `~/.local/share/t3code-customize`，原始碼與記錄檔在 `~/.cache/t3code-customize`。
- **Windows 的檔案位置**：資料與建置結果在 `%LOCALAPPDATA%\t3code-customize`，原始碼與記錄檔在其中的 `cache` 子資料夾。在 WSL 中建置時，建置結果與啟動器狀態同樣在這裡，原始碼、記錄檔與設定則留在 WSL 中（`~/.cache/t3code-customize`、`~/.config/t3code-customize`），指令位於 `~/.local/bin/t3code-customize`。

## 開發檢查

```sh
python -m unittest discover -s tests -v
python t3code-customize verify            # 驗證每一組 patch
python t3code-customize verify --patch-set 0.1.13
```

Linux 請用 `python3`。第一個指令用測試資料驗證 App 配置、分離與合併的封存檔、更新後的回退、檔案鎖、指令包裝程式與完整性中繼資料。在 Windows 上還會測試實際的 PE 資源 API。第二個指令會把所有 patch 套用到基準 commit，並執行 `checks.json` 中的所有測試與型別檢查；它會下載 upstream 原始碼與相依套件。

CI 會在 Linux、macOS 與 Windows 上執行平台測試，並在 Linux 與 macOS 上驗證 upstream patch。測試資料的驗證與實際桌面啟動、模型供應商整合的驗證是分開進行的。

## 授權

MIT，與 T3 Code 相同。
