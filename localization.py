"""Shared translations for setup, sample preview and monitoring overlays."""
import re
from string import Formatter

LANGUAGES = {"en": "English", "ja": "日本語", "ko": "한국어", "zh": "简体中文"}
_language = "ko"
# Korean / English / Japanese / Simplified Chinese. Korean UI uses short labels.
ROWS = [
    ("모니터링 준비", "Monitoring setup", "モニタリング設定", "监测设置"),
    ("창 선택 · 판정 설정 · 화면 확인", "Select windows · Set limits · Preview", "ウィンドウ選択・判定設定・プレビュー", "选择窗口 · 设置阈值 · 预览"),
    ("설정 중", "Setup", "設定中", "设置中"),
    ("연결할 창", "Source windows", "対象ウィンドウ", "来源窗口"),
    ("OBS 화면", "OBS window", "OBS画面", "OBS窗口"),
    ("게임 창", "Game window", "ゲーム画面", "游戏窗口"),
    ("OBS: 점 감지 / 게임: 타이머", "OBS: target / Game: timer", "OBS：点検出 / ゲーム：タイマー", "OBS：目标 / 游戏：计时器"),
    ("창 목록 새로고침", "Refresh windows", "ウィンドウ一覧更新", "刷新窗口"),
    ("모니터링 방식", "Monitoring mode", "モニタリング方式", "监测模式"),
    ("위치 추적", "Position tracking", "位置追跡", "位置追踪"),
    ("원형 판정", "Circle judging", "円形判定", "圆形判定"),
    ("마지막 정상 감지 좌표와 비교", "Compare with last valid detection", "直前の有効な検出位置と比較", "与上次有效检测位置比较"),
    ("고정된 원 기준 이탈 감지 · 채점", "Fixed-circle alerts and grading", "固定円からの逸脱検出・評価", "固定圆范围警报与评分"),
    ("원형 판정 기준", "Circle limits", "円形判定基準", "圆形判定范围"),
    ("원 반지름", "Radius", "半径", "半径"),
    ("채점 기준", "Grading", "評価基準", "评分标准"),
    ("원 밖 감지 비율 · 0.05 = 5%", "Outside-detection ratio · 0.05 = 5%", "円外の検出割合・0.05 = 5%", "圆外检测比例 · 0.05 = 5%"),
    ("이동량 경고", "Movement alert", "移動量警告", "移动量警报"),
    ("X · Y 개별", "Separate X / Y", "X・Y個別", "分别设置X/Y"),
    ("합산 거리", "Distance", "合成距離", "合成距离"),
    ("기록", "Recording", "記録", "记录"),
    ("게임 타이머로 자동 기록", "Record with game timer", "ゲームタイマーで自動記録", "按游戏计时器自动记录"),
    ("{a}–{b}초 시작 · {c}–{d}초 종료", "Start {a}–{b}s · Stop {c}–{d}s", "{a}–{b}秒で開始・{c}–{d}秒で終了", "{a}–{b}秒开始 · {c}–{d}秒结束"),
    ("R 기록 · M 음소거 · Q/ESC 설정", "R Record · M Mute · Q/ESC Setup", "R 記録・M 消音・Q/ESC 設定", "R 记录 · M 静音 · Q/ESC 设置"),
    ("모니터링 시작", "Start monitoring", "モニタリング開始", "开始监测"),
    ("준비 완료 · 시작 시 설정 저장", "Ready · Settings saved on start", "準備完了・開始時に設定保存", "就绪 · 开始时保存设置"),
    ("OBS 화면과 게임 창 선택", "Select OBS and game windows", "OBSとゲーム画面を選択", "选择OBS和游戏窗口"),
    ("활성 모드", "ACTIVE MODE", "使用中のモード", "当前模式"),
    ("GitHub 저장소", "GitHub repository", "GitHubリポジトリ", "GitHub仓库"),
    ("언어", "Language", "言語", "语言"),
    ("미리보기", "Preview", "プレビュー", "预览"),
    ("실제 화면", "Live view", "実際の画面", "实时画面"),
    ("샘플", "Sample", "サンプル", "示例"),
    ("크게 보기", "Enlarge", "拡大", "放大"),
    ("다시 감지", "Detect again", "再検出", "重新检测"),
    ("일시정지", "Pause", "一時停止", "暂停"),
    ("재개", "Resume", "再開", "继续"),
    ("미리보기 일시정지", "Preview paused", "プレビュー停止中", "预览已暂停"),
    ("미리보기 · 기록/소리 없음", "Preview · No recording or sound", "プレビュー・記録/音声なし", "预览 · 不记录、不发声"),
    ("OBS 창 선택", "Select an OBS window", "OBS画面を選択", "选择OBS窗口"),
    ("OBS 창 최소화 해제", "Restore the OBS window", "OBSの最小化を解除", "还原OBS窗口"),
    ("선택한 OBS 창 없음", "Selected OBS window not found", "選択したOBS画面が見つからない", "所选OBS窗口不存在"),
    ("캡처 실패: {error}", "Capture failed: {error}", "キャプチャ失敗：{error}", "捕获失败：{error}"),
    ("검은 감지 영역 없음", "No black detection area", "黒い検出領域なし", "未找到黑色检测区域"),
    ("감지 영역 {w} × {h}px · {state}", "Area {w} × {h}px · {state}", "検出領域 {w} × {h}px・{state}", "检测区域 {w} × {h}px · {state}"),
    ("정상 감지", "Detected", "検出中", "已检测"),
    ("미감지 · 마지막 정상 좌표 유지", "No detection · Last valid position retained", "未検出・直前の有効座標を保持", "未检测 · 保留上次有效坐标"),
    ("샘플 크기", "Sample size", "サンプルサイズ", "示例尺寸"),
    ("16:9 기본", "16:9 default", "16:9 標準", "16:9 默认"),
    ("커스텀 · 직접 입력", "Custom dimensions", "カスタム・直接入力", "自定义尺寸"),
    ("OBS 감지 영역", "OBS detection area", "OBS検出領域", "OBS检测区域"),
    ("OBS 크기 불러오기", "Load OBS size", "OBSサイズ取得", "读取OBS尺寸"),
    ("커스텀 샘플", "Custom sample", "カスタムサンプル", "自定义示例"),
    ("16:9 샘플", "16:9 sample", "16:9 サンプル", "16:9示例"),
    ("클릭/드래그로 위치 변경", "Click or drag to move the point", "クリック/ドラッグで位置変更", "点击或拖动以移动位置"),
    ("중앙: 원 중심 · 골드: 판정 범위", "Center: circle origin · Gold: boundary", "中央：円の中心・金：判定範囲", "中心：圆心 · 金色：判定范围"),
    ("중앙: 직전 정상 위치 · 라일락: 허용 범위", "Center: last valid point · Lilac: allowed range", "中央：直前の有効位置・紫：許容範囲", "中心：上次有效位置 · 紫色：允许范围"),
    ("샘플 점 초기화", "Reset sample point", "サンプル点を初期化", "重置示例点"),
    ("샘플 크기는 실제 판정에 영향 없음", "Sample size does not change live detection", "サンプルサイズは実際の判定に影響なし", "示例尺寸不影响实际检测"),
    ("양수 픽셀 값 입력", "Enter positive pixel values", "正のピクセル値を入力", "输入正数像素值"),
    ("반지름: 1 이상 정수", "Radius: integer of at least 1", "半径：1以上の整数", "半径：不小于1的整数"),
    ("OBS 크기 확인 실패: {error}", "OBS size unavailable: {error}", "OBSサイズ取得失敗：{error}", "无法读取OBS尺寸：{error}"),
    ("원 이탈 · 경고", "Outside circle · Alert", "円外・警告", "超出圆形 · 警报"),
    ("원 안 · 경계 포함", "Inside circle · Boundary included", "円内・境界を含む", "圆形内 · 包含边界"),
    ("중심 X {x:+.1f}px · Y {y:+.1f}px\n거리 {d:.1f}px / 반지름 {r}px · {result}", "Center X {x:+.1f}px · Y {y:+.1f}px\nDistance {d:.1f}px / Radius {r}px · {result}", "中心 X {x:+.1f}px・Y {y:+.1f}px\n距離 {d:.1f}px / 半径 {r}px・{result}", "中心 X {x:+.1f}px · Y {y:+.1f}px\n距离 {d:.1f}px / 半径 {r}px · {result}"),
    ("경고 · 임계값 이상", "Alert · At or above limit", "警告・しきい値以上", "警报 · 达到或超过阈值"),
    ("허용 범위", "Within limits", "許容範囲", "允许范围内"),
    ("경고 OFF", "Alert OFF", "警告 OFF", "警报 OFF"),
    ("ΔX {x:+.1f}px · ΔY {y:+.1f}px · 거리 {d:.1f}px\n{result}", "ΔX {x:+.1f}px · ΔY {y:+.1f}px · Distance {d:.1f}px\n{result}", "ΔX {x:+.1f}px・ΔY {y:+.1f}px・距離 {d:.1f}px\n{result}", "ΔX {x:+.1f}px · ΔY {y:+.1f}px · 距离 {d:.1f}px\n{result}"),
    ("선택한 창 없음 · 목록 새로고침 필요", "Selected window closed · Refresh the list", "選択した画面なし・一覧を更新", "所选窗口已关闭 · 刷新列表"),
    ("입력값 확인", "Check input", "入力値の確認", "检查输入"),
    ("설정값 오류 · 모니터링 시작 취소", "Invalid settings · Monitoring not started", "設定値エラー・開始を中止", "设置错误 · 未开始监测"),
    ("OBS 연결 상태 확인", "Check OBS connection", "OBS接続状態を確認", "检查OBS连接"),
]

ROWS.extend([
    ("활동 로그", "Activity log", "動作ログ", "运行日志"),
    ("사용법", "Guide", "使い方", "使用指南"),
    ("프로그램 시작", "Application started", "アプリ起動", "程序已启动"),
    ("설정 · {name}: {value}", "Set · {name}: {value}", "設定・{name}: {value}", "设置 · {name}: {value}"),
    ("오류: {error}", "Error: {error}", "エラー: {error}", "错误：{error}"),
    ("입력 연결 복구", "Input connection restored", "入力接続が復旧", "输入连接已恢复"),
    ("원형 비프음", "Circle beep", "円形判定ビープ音", "圆形提示音"),
    ("이동량 비프음", "Movement beep", "移動量ビープ音", "移动提示音"),
    ("판정 방식", "Threshold method", "判定方式", "判定方式"),
    ("알림음 파일 없음", "Alert sound file missing", "通知音ファイルなし", "提示音文件不存在"),
    ("기록 중 {time}", "Recording {time}", "記録中 {time}", "记录中 {time}"),
    ("샘플 영상 재생", "Play sample video", "サンプル動画を再生", "播放示例视频"),
    ("샘플 중지 · 실제 화면으로", "Stop sample · Back to live view", "サンプル停止・実画面へ", "停止示例 · 返回实际画面"),
    ("샘플 영상 · 반복", "Sample video · Loop", "サンプル動画・ループ", "示例视频 · 循环"),
    ("샘플 영상 재생 실패", "Sample video playback failed", "サンプル動画の再生失敗", "示例视频播放失败"),
    ("측정 가이드", "Guide", "計測ガイド", "测量参考线"),
    ("비프음 설정 OFF", "Beep setting OFF", "ビープ音設定 OFF", "提示音设置 OFF"),
    ("캡처 영역 없음", "Empty capture area", "キャプチャ領域なし", "无捕获区域"),
    ("창 캡처 실패", "Window capture failed", "ウィンドウのキャプチャ失敗", "窗口捕获失败"),
    ("설정 저장 실패", "Settings save failed", "設定保存失敗", "设置保存失败"),
    ("프로그램 자체 창은 캡처 불가", "Cannot capture this application's own window", "自身のウィンドウはキャプチャ不可", "无法捕获程序自身窗口"),
    ("작업 실패", "Action failed", "操作失敗", "操作失败"),
    ("비프음", "Beep", "ビープ音", "提示音"),
    ("모니터링 중", "Monitoring", "モニタリング中", "监测中"),
    ("모니터링 종료", "Stop monitoring", "モニタリング終了", "停止监测"),
    ("좌표", "Position", "座標", "坐标"),
    ("이동량", "Movement", "移動量", "移动量"),
    ("타이머", "Timer", "タイマー", "计时器"),
    ("기록 대기", "Recording standby", "記録待機", "等待记录"),
    ("기록 시작", "Start recording", "記録開始", "开始记录"),
    ("기록 종료", "Stop recording", "記録終了", "停止记录"),
    ("단축키: R 기록 · M 음소거 · ESC 종료 · C 타이머 저장", "Keys: R Record · M Mute · ESC Stop · C Save timer", "キー：R 記録・M 消音・ESC 終了・C タイマー保存", "快捷键：R 记录 · M 静音 · ESC 停止 · C 保存计时器"),
    ("기록 저장 · {grade} · 감지 {n}프레임 · 경고 {beeps}회", "Saved · {grade} · {n} detections · {beeps} alerts", "保存済・{grade}・検出 {n}フレーム・警告 {beeps}回", "已保存 · {grade} · 检测 {n}帧 · 警报 {beeps}次"),
    ("입력값 확인 · 마지막 유효 설정 유지", "Invalid input · Keeping last valid settings", "入力値を確認・直前の有効設定を維持", "检查输入 · 保留上次有效设置"),
    ("OBS 창 없음 또는 최소화", "OBS window closed or minimized", "OBS画面なし・最小化中", "OBS窗口已关闭或最小化"),
    ("필수 · 창 선택", "Required · Select a window", "必須・ウィンドウ選択", "必填 · 选择窗口"),
    ("창 없음 · 다시 선택", "Window unavailable · Select again", "画面なし・再選択", "窗口不存在 · 重新选择"),
    ("판정 설정값 확인", "Check detection limits", "判定設定値を確認", "检查检测阈值"),
    ("처리 중", "Processing", "処理中", "处理中"),
    ("설정 변경 실시간 적용", "Settings apply live", "設定変更を即時反映", "设置实时生效"),
    ("필수 설정: {items}", "Required: {items}", "必須設定：{items}", "必填设置：{items}"),
    ("판정 설정", "Detection settings", "判定設定", "检测设置"),
    ("설정 접기", "Hide settings", "設定を閉じる", "收起设置"),
    ("설정 펼치기", "Show settings", "設定を開く", "展开设置"),
    ("기록 저장 실패", "Recording save failed", "記録保存失敗", "记录保存失败"),
    ("기록 폴더", "Recordings", "記録フォルダー", "记录文件夹"),
])

# English strings already emitted by the monitoring renderer. Translate them at
# the text-rendering boundary so live preview and real monitoring remain identical.
OVERLAYS = [
    ("설정으로", "Back to setup", "設定に戻る", "返回设置"),
    ("기록 시작/종료", "Record on/off", "記録開始/停止", "开始/停止记录"),
    ("음소거", "Mute", "消音", "静音"),
    ("반지름", "Radius", "半径", "半径"),
    ("타이머 영역 저장", "Save game timer ROI", "タイマー領域保存", "保存计时器区域"),
    ("단축키", "CONTROLS", "ショートカット", "快捷键"),
    ("원형 판정", "MODE: CIRCLE JUDGING", "円形判定", "圆形判定"),
    ("위치 추적", "MODE: POSITION ONLY", "位置追跡", "位置追踪"),
    ("대기", "IDLE", "待機", "待机"),
    ("자동 OFF", "AUTO OFF", "自動 OFF", "自动 OFF"),
    ("자동 대기", "AUTO ARMED", "自動 待機", "自动待机"),
    ("자동 기록", "AUTO REC", "自動 記録", "自动记录"),
    ("자동 완료", "AUTO DONE", "自動 完了", "自动完成"),
    ("반지름 {n}", "Radius {n}", "半径 {n}", "半径 {n}"),
    ("음소거 ON", "Muted ON", "消音 ON", "静音 ON"),
    ("음소거 OFF", "Muted OFF", "消音 OFF", "静音 OFF"),
    ("이동량 경고 OFF", "Delta feedback OFF", "移動量警告 OFF", "移动量警报 OFF"),
    ("합산 거리 ≥ {n}px", "Delta distance >= {n} px", "合成距離 ≥ {n}px", "合成距离 ≥ {n}px"),
    ("|ΔX| ≥ {x} 또는 |ΔY| ≥ {y}px", "|dX| >= {x} OR |dY| >= {y} px", "|ΔX| ≥ {x} または |ΔY| ≥ {y}px", "|ΔX| ≥ {x} 或 |ΔY| ≥ {y}px"),
    ("정상 감지", "TRACKING", "検出中", "已检测"),
    ("미감지 · 마지막 정상 좌표 유지", "NO DETECTION - holding last values", "未検出・直前の有効座標を保持", "未检测 · 保留上次有效坐标"),
    ("이동량 경고: X {x} Y {y}px", "DELTA ALERT: X {x} Y {y} px", "移動量警告：X {x} Y {y}px", "移动量警报：X {x} Y {y}px"),
    ("좌표: -- (첫 감지 대기)", "Position: -- (waiting for first detection)", "座標：--（初回検出待ち）", "坐标：--（等待首次检测）"),
    ("좌표: X {x}  Y {y}px", "Position: X {x}  Y {y} px", "座標：X {x}  Y {y}px", "坐标：X {x}  Y {y}px"),
    ("이동량: -- (다음 감지 대기)", "Delta: -- (waiting for next detection)", "移動量：--（次の検出待ち）", "移动量：--（等待下次检测）"),
    ("이동량: X {x}  Y {y}px", "Delta: X {x}  Y {y} px", "移動量：X {x}  Y {y}px", "移动量：X {x}  Y {y}px"),
    ("방향: 오른쪽 +X, 아래 +Y", "Axes: right +X, down +Y", "方向：右 +X、下 +Y", "方向：右 +X、下 +Y"),
    ("검은 감지 영역 탐색 중", "Looking for play area (black box)...", "黒い検出領域を探索中", "正在查找黑色检测区域"),
    ("수동 기록 시작", "Manual recording started", "手動記録開始", "手动记录开始"),
    ("자동 기록 시작", "Auto recording started", "自動記録開始", "自动记录开始"),
    ("기록 종료", "Recording stopped", "記録終了", "记录结束"),
    ("음소거 적용", "Mute enabled", "消音有効", "已静音"),
    ("음소거 해제", "Mute disabled", "消音解除", "已取消静音"),
    ("원 반지름: {n}", "Circle radius: {n}", "円の半径：{n}", "圆半径：{n}"),
    ("판정 프레임 없음", "No judged frames (circle off or no detection)", "判定フレームなし", "无有效判定帧"),
    ("타이머 영역 저장 실패", "Failed to save timer ROI", "タイマー領域保存失敗", "计时器区域保存失败"),
    ("게임 화면 없음", "No game frame yet", "ゲーム画面なし", "暂无游戏画面"),
]
_catalog = {row[0]: dict(zip(("ko", "en", "ja", "zh"), row)) for row in ROWS}
for row in OVERLAYS:
    _catalog.setdefault(row[0], dict(zip(("ko", "en", "ja", "zh"), row)))
_overlay = {row[1]: dict(zip(("ko", "en", "ja", "zh"), row)) for row in OVERLAYS}
_patterns = []
for source, translations in _overlay.items():
    if "{" not in source:
        continue
    pattern = ""
    for literal, field, _, _ in Formatter().parse(source):
        pattern += re.escape(literal)
        if field:
            pattern += f"(?P<{field}>.+?)"
    _patterns.append((re.compile("^" + pattern + "$"), translations))


def set_language(language):
    global _language
    _language = language if language in LANGUAGES else "ko"


def get_language():
    return _language


def t(key, **values):
    return _catalog.get(key, {}).get(_language, key).format(**values)


def overlay_text(text):
    if text.endswith(" [MUTED]"):
        return overlay_text(text[:-8]) + " [" + t("음소거") + "]"
    if text.startswith("Axes: right +X, down +Y  |"):
        return overlay_text("Axes: right +X, down +Y") + text[len("Axes: right +X, down +Y"):]
    if text in _overlay:
        return _overlay[text][_language]
    for pattern, translations in _patterns:
        match = pattern.match(text)
        if match:
            return translations[_language].format(**match.groupdict())
    return text
