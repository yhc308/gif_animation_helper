# ===================================================
# 이름: Gif_Animation_Sampler (GIF 애니메이션 샘플러)
# 버전: v0.515 (모션 리스트 아이템 높이 추가 조정)
# 제작자: 윤희찬 (원본) / AI 협업 수정
# 설명: GIF 파일의 프레임별 딜레이(ms)를 시각적으로 확인하고,
#       키프레임을 기반으로 모션 단위로 분할 및 분석할 수 있는 도구입니다.
#       .gifproj 프로젝트 파일(JSON 형식)을 통해 키프레임 및 모션 설정을 저장/로드를 지원합니다.
#       등록된 키프레임을 기반으로 각 모션 구간을 별도의 GIF 파일로 출력하며,
#       프레임 설명을 TXT 파일로도 출력할 수 있습니다.
#       최하단에 상태 표시줄을 추가하여 현재 작업 상태 및 진행(간이)을 사용자에게 안내합니다.
#       재생 제어 버튼 아이콘은 "buttons" 하위 폴더의 PNG 파일을 사용합니다.
# 사용 라이브러리: PySide6 (UI 구성), Pillow (GIF 프레임 처리 및 출력)
# Python 버전: 3.10.11 (권장)
# ===================================================

# PySide6 GUI 모듈 및 표준 라이브러리 임포트
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QListWidget, QLineEdit, QFileDialog, QScrollArea, QGridLayout, QMessageBox,
    QSizePolicy, QListWidgetItem, QInputDialog, QLayout, QStatusBar,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QMenu, QGraphicsOpacityEffect
)
from PySide6.QtGui import QPixmap, QImage, QColor, QFont, QIcon, QFontMetrics, QPainter, QAction, QKeySequence
from PySide6.QtCore import Qt, QSize, QEvent, QTimer, Signal, QPointF, QObject 
import sys, os
from PIL import Image, ImageSequence, ImagePalette
import json
import traceback
from functools import partial
import bisect
import math
import re 

# 클릭 시 어둡게 할 색상 맵 (원본 HEX -> 약 20% 어두운 HEX) - FrameButton은 더 이상 사용 안 함
DARKER_COLOR_MAP = {
    # Original : 20% Darker (RGB * 0.8)
    "#303030": "#262626",
    "#3C3C3C": "#303030",
    "#2A2A2A": "#212121",
    "#4CAF50": "#3C8C40",
    "#F44336": "#C3352B",
    "#FFFFFF": "#CCCCCC", 
    "#202020": "#191919", 
    "#353535": "#2A2A2A", 
    "#404040": "#333333", 
}

class CustomStyledButton(QPushButton): # 파일 관리, 재생 제어, 추출, 메인 키프레임 버튼용
    def __init__(self, text_or_icon=None, parent=None):
        if isinstance(text_or_icon, QIcon):
            super().__init__(text_or_icon, "", parent)
        elif isinstance(text_or_icon, str):
            super().__init__(text_or_icon, parent)
        else:
            super().__init__(parent)
        
        self._normal_style_sheet = self.styleSheet() 
        self._pressed_style_sheet = self._derive_pressed_style(self._normal_style_sheet)
        self._is_currently_pressed = False

    def setCustomStyles(self, normal_style, pressed_style):
        self._normal_style_sheet = normal_style
        self._pressed_style_sheet = pressed_style
        if not self._is_currently_pressed:
            super().setStyleSheet(self._normal_style_sheet)
        else: 
            super().setStyleSheet(self._pressed_style_sheet)

    def setStyleSheet(self, styleSheet):
        super().setStyleSheet(styleSheet) 
        self._normal_style_sheet = styleSheet 
        self._pressed_style_sheet = self._derive_pressed_style(self._normal_style_sheet)
        if self._is_currently_pressed:
            pass 
        else:
            pass

    def _derive_pressed_style(self, base_style):
        current_bg_hex = CustomStyledButton._extract_background_color_hex(base_style)
        if current_bg_hex: 
            darker_bg_hex = DARKER_COLOR_MAP.get(current_bg_hex.upper()) 
            if darker_bg_hex:
                return CustomStyledButton._replace_background_color_in_style(base_style, darker_bg_hex)
        return base_style 

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._is_currently_pressed = True
            if self._pressed_style_sheet: 
                 super().setStyleSheet(self._pressed_style_sheet)
        super().mousePressEvent(event) 

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled() and self._is_currently_pressed:
            self._is_currently_pressed = False
            super().setStyleSheet(self._normal_style_sheet) 
        super().mouseReleaseEvent(event) 

    @staticmethod
    def _extract_background_color_hex(style_sheet_str):
        if not style_sheet_str: return None
        matches = re.findall(r"background-color:\s*(#[0-9a-fA-F]{6})", style_sheet_str, re.IGNORECASE)
        if matches:
            return matches[0] 
        return None

    @staticmethod
    def _replace_background_color_in_style(original_style, new_bg_color_hex):
        if not original_style: original_style = "" 
        replaced_style, num_replacements = re.subn(
            r"(background-color:\s*)(#[0-9a-fA-F]{6})", 
            rf"\g<1>{new_bg_color_hex}", 
            original_style,
            count=1, 
            flags=re.IGNORECASE
        )
        if num_replacements > 0: 
            return replaced_style
        else: 
            if original_style and not original_style.strip().endswith(';'):
                original_style += ";"
            return f"{original_style.strip()} background-color: {new_bg_color_hex};".strip()

class FrameButton(QPushButton): 
    doubleClickedWithIndex = Signal(int) 

    def __init__(self, text, index, parent=None):
        super().__init__(text, parent) 
        self.index = index 

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClickedWithIndex.emit(self.index)
        super().mouseDoubleClickEvent(event) 

class CustomMotionListWidget(QListWidget):
    def __init__(self, parent_ui, parent=None):
        super().__init__(parent)
        self.parent_ui = parent_ui 

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint()) 
            if item:
                self.parent_ui.edit_motion_name(item)
                event.accept() 
                return
        super().mouseDoubleClickEvent(event) 

class OpacityButton(QPushButton):
    def __init__(self, icon_path="", parent=None):
        super().__init__(parent)
        if icon_path:
            self.setIcon(QIcon(icon_path))

        self.opacity_effect = QGraphicsOpacityEffect(self) 
        self.setGraphicsEffect(self.opacity_effect) 

        self.base_opacity_enabled = 0.20  
        self.base_opacity_disabled = 0.05 
        self.hover_opacity = 0.40         
        self.pressed_opacity = 0.50       
        
        self._is_pressed = False 
        self._is_hovered = False 

        self._update_opacity() 

    def _update_opacity(self):
        if not self.isEnabled():
            self.opacity_effect.setOpacity(self.base_opacity_disabled)
        elif self._is_pressed:
            self.opacity_effect.setOpacity(self.pressed_opacity)
        elif self._is_hovered:
            self.opacity_effect.setOpacity(self.hover_opacity)
        else:
            self.opacity_effect.setOpacity(self.base_opacity_enabled)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        if enabled:
            self._is_hovered = self.underMouse() 
        else:
            self._is_hovered = False 
        self._update_opacity()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._is_hovered = True
        if self.isEnabled(): 
            self._update_opacity()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._is_hovered = False
        self._update_opacity() 

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._is_pressed = True
            self._update_opacity()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._is_pressed = False
            self._is_hovered = self.rect().contains(event.position().toPoint())
            self._update_opacity()

class GifSplitterUI(QWidget):
    def __init__(self):
        super().__init__() 
        self.setWindowTitle("Gif_Animation_Sampler v0.515") 
        self.setStyleSheet("background-color: #202020; color: white;") 
        self.setMinimumSize(1280, 720) 

        self.gif_path = None 
        self.keyframes = {} 
        self.frame_buttons = [] 
        self.selected_index = None 
        self.unsaved_changes = False 
        self.original_gif_info = {} 
        self.all_frame_data = [] 
        self.original_gif_palette_data = None 
        self.pressed_motion_list_item = None 
        self.pressed_frame_preview_item = None 

        self.graphics_view = None
        self.graphics_scene = None
        self.pixmap_item = None  
        
        self.scale_levels = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0, 5.0, 6.0, 7.0, 8.0]
        try:
            self.current_scale_index = self.scale_levels.index(1.0) 
        except ValueError: 
            self.current_scale_index = 3 
        self.current_scale_factor = self.scale_levels[self.current_scale_index]
        self.current_transformation_mode = Qt.TransformationMode.SmoothTransformation 
        
        self.preview_zoom_in_btn = None
        self.preview_zoom_out_btn = None
        self.preview_home_btn = None
        self.preview_button_container = None

        self.playback_timer = QTimer(self) 
        self.playback_timer.setSingleShot(True) 
        self.current_playback_frame_index = -1 
        self.is_looping_specific_motion = False 
        self.active_motion_start_index = -1   
        self.active_motion_end_index = -1     

        self.status_bar = QStatusBar() 
        self.status_label = QLabel("준비 완료. 새 프로젝트를 시작하거나 GIF 파일을 불러오세요.") 

        self.base_font_size = QApplication.font().pointSize()
        if self.base_font_size <= 0: self.base_font_size = 10 

        status_font_size = int(self.base_font_size * 0.85) 
        if status_font_size <=0 : status_font_size = 8 

        self.status_label_font = QFont(QApplication.font().family(), status_font_size) 

        self.status_label_default_style = f"font-size: {status_font_size}pt; color: rgba(204, 204, 204, 179); padding-left: 6px; padding-right: 6px; background-color: transparent;"
        self.status_label_loading_style = f"font-size: {status_font_size}pt; color: rgba(204, 204, 204, 179); padding-left: 6px; padding-right: 6px; background-color: #2f3c53;" 
        self.status_label_complete_style = f"font-size: {status_font_size}pt; color: rgba(204, 204, 204, 179); padding-left: 6px; padding-right: 6px; background-color: #2f3c53;" 

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True) 
        self._status_timer.timeout.connect(self._clear_status_loading_style) 
        self._current_status_message_for_timer = "" 

        self._init_playback_buttons() 
        self._init_preview_control_buttons() 

        self.add_keyframe_style_base = {"background-color": "#4CAF50", "color": "white", "border-radius": "5px", "padding": "8px"}
        self.remove_keyframe_style_base = {"background-color": "#F44336", "color": "white", "border-radius": "5px", "padding": "8px"}

        self.add_keyframe_style = self._generate_style_str_from_dict(self.add_keyframe_style_base)
        self.remove_keyframe_style = self._generate_style_str_from_dict(self.remove_keyframe_style_base)

        self.init_ui() 
        self.connect_signals() 
        self._update_primary_keyframe_button_ui() 
        self._update_preview_button_states() 

        self.installEventFilter(self) 
        if self.graphics_view:
            self.graphics_view.viewport().installEventFilter(self)

    def _generate_style_str_from_dict(self, style_dict):
        return "; ".join([f"{key}: {value}" for key, value in style_dict.items()]) + ";"

    def _get_pressed_style_from_normal(self, normal_style_str, original_bg_color_key=None):
        current_bg_hex = None
        if original_bg_color_key and original_bg_color_key.upper() in DARKER_COLOR_MAP:
            current_bg_hex = original_bg_color_key.upper()
        else: 
            extracted_hex = CustomStyledButton._extract_background_color_hex(normal_style_str)
            if extracted_hex:
                current_bg_hex = extracted_hex.upper()

        if current_bg_hex:
            darker_bg_hex = DARKER_COLOR_MAP.get(current_bg_hex) 
            if darker_bg_hex:
                return CustomStyledButton._replace_background_color_in_style(normal_style_str, darker_bg_hex)
        return normal_style_str 

    def _init_playback_buttons(self):
        self.icon_base_path = "buttons" 
        self.icon_size = QSize(20, 20) 
        self.button_size = QSize(32, 32)

        self.prev_btn = CustomStyledButton() 
        self.prev_btn._icon_path_normal = os.path.join(self.icon_base_path, "3previous.png") 
        self.prev_btn._icon_path_pressed = os.path.join(self.icon_base_path, "3previous_pressed.png") 
        self.prev_btn.setIcon(QIcon(self.prev_btn._icon_path_normal)) 
        self.prev_btn.setToolTip("이전 모션의 시작점으로 이동") 

        self.play_pause_btn = CustomStyledButton() 
        self.play_pause_btn.setCheckable(True) 
        self.play_pause_btn._icon_path_normal_off = os.path.join(self.icon_base_path, "1play.png") 
        self.play_pause_btn._icon_path_pressed_off = os.path.join(self.icon_base_path, "1play_pressed.png") 
        self.play_pause_btn._icon_path_normal_on = os.path.join(self.icon_base_path, "2stop.png") 
        self.play_pause_btn._icon_path_pressed_on = os.path.join(self.icon_base_path, "2stop_pressed.png") 
        self.play_pause_btn.setIcon(QIcon(self.play_pause_btn._icon_path_normal_off)) 
        self.play_pause_btn.setToolTip("재생 (전체 반복)") 

        self.next_btn = CustomStyledButton() 
        self.next_btn._icon_path_normal = os.path.join(self.icon_base_path, "5next.png") 
        self.next_btn._icon_path_pressed = os.path.join(self.icon_base_path, "5next_pressed.png") 
        self.next_btn.setIcon(QIcon(self.next_btn._icon_path_normal)) 
        self.next_btn.setToolTip("다음 모션의 시작점으로 이동") 

        self.loop_btn = CustomStyledButton() 
        self.loop_btn.setCheckable(True) 
        self.loop_btn._icon_path_normal_off = os.path.join(self.icon_base_path, "4loop.png") 
        self.loop_btn._icon_path_pressed_off = os.path.join(self.icon_base_path, "4loop_pressed.png") 
        self.loop_btn._icon_path_normal_on = os.path.join(self.icon_base_path, "4loop_pressed.png") 
        self.loop_btn._icon_path_pressed_on = os.path.join(self.icon_base_path, "4loop_pressed.png") 
        self.loop_btn.setIcon(QIcon(self.loop_btn._icon_path_normal_off)) 
        self.loop_btn.setToolTip("현재 모션 반복 (활성화 시)") 

        self.playback_buttons_group = [
            self.prev_btn, self.play_pause_btn, self.next_btn, self.loop_btn
        ]
        
        normal_bg_key = "#3C3C3C" 
        base_playback_style_dict = {"border": "1px solid #2A2A2A", "border-radius": "5px", "padding": "0px"}
        
        normal_style_str = self._generate_style_str_from_dict({**base_playback_style_dict, "background-color": normal_bg_key})
        pressed_style_str = self._get_pressed_style_from_normal(normal_style_str, normal_bg_key)

        for btn in self.playback_buttons_group:
            btn.setIconSize(self.icon_size) 
            btn.setFixedSize(self.button_size)
            btn.setCustomStyles(normal_style_str, pressed_style_str)

    def _init_preview_control_buttons(self):
        preview_icon_size = QSize(30, 30) 
        preview_button_size = QSize(48, 48)
        
        button_style = """
            OpacityButton { 
                background-color: transparent; 
                border: none; 
                padding: 0px; 
            }
        """
        self.preview_zoom_in_btn = OpacityButton(os.path.join(self.icon_base_path, "10Plus.png"))
        self.preview_zoom_in_btn.setToolTip("미리보기 확대 (+)")
        
        self.preview_zoom_out_btn = OpacityButton(os.path.join(self.icon_base_path, "11minus.png"))
        self.preview_zoom_out_btn.setToolTip("미리보기 축소 (-)")

        self.preview_home_btn = OpacityButton(os.path.join(self.icon_base_path, "12home.png"))
        self.preview_home_btn.setToolTip("미리보기 초기화 (1.0x, 중앙)")

        self.preview_control_buttons_group = [
            self.preview_zoom_in_btn, self.preview_zoom_out_btn, self.preview_home_btn
        ]

        for btn in self.preview_control_buttons_group:
            btn.setIconSize(preview_icon_size) 
            btn.setFixedSize(preview_button_size) 
            btn.setStyleSheet(button_style)

    def _get_status_font(self):
        font = QFont(QApplication.font()) 
        default_point_size = font.pointSize() 
        if default_point_size <= 0:
            default_pixel_size = font.pixelSize()
            if default_pixel_size <= 0:
                default_pixel_size = 13 
            font.setPixelSize(int(default_pixel_size * 0.85)) 
        else:
            font.setPointSize(int(default_point_size * 0.85)) 
        return font 

    def _format_frame_number(self, frame_idx):
        if frame_idx < 100: 
            return f"{frame_idx:02d}F"
        elif frame_idx < 1000: 
            return f"{frame_idx:03d}F"
        else: 
            return f"{frame_idx:04d}F"

    def init_ui(self):
        main_app_layout = QVBoxLayout()
        main_app_layout.setContentsMargins(0, 0, 0, 0) 
        main_app_layout.setSpacing(0) 

        content_area_widget = QWidget() 
        content_area_layout = QVBoxLayout(content_area_widget) 
        content_area_layout.setContentsMargins(6, 6, 6, 6) 
        content_area_layout.setSpacing(6) 

        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #202020; 
                border-top: 1px solid #353535; 
                padding-top: 0px; 
                padding-bottom: 0px; 
                padding-left: 0px; 
                padding-right: 0px; 
            }
            QStatusBar::item { border: none; } 
        """)
        self.status_label.setFont(self.status_label_font) 
        self.status_label.setStyleSheet(self.status_label_default_style) 
        self.status_bar.addWidget(self.status_label, 1) 

        top_bar_layout = QGridLayout()
        top_bar_layout.setContentsMargins(6, 0, 6, 0) 
        top_bar_layout.setSpacing(0) 

        self.new_project_btn = CustomStyledButton("새 프로젝트 시작")
        self.load_btn = CustomStyledButton("GIF 불러오기")
        self.save_btn = CustomStyledButton("설정 저장")
        self.load_cfg_btn = CustomStyledButton("설정 불러오기")

        file_project_buttons_widget = QWidget() 
        file_project_buttons_layout = QHBoxLayout(file_project_buttons_widget) 
        file_project_buttons_layout.setContentsMargins(0,0,0,0) 
        file_project_buttons_layout.setSpacing(6) 

        file_project_buttons = [
            self.new_project_btn, self.load_btn, self.save_btn, self.load_cfg_btn
        ]
        
        file_btn_original_bg_key = "#303030"
        file_btn_style_attrs = {"color": "white", "border-radius": "5px", "padding": "0 10px"}
        
        file_btn_normal_style = self._generate_style_str_from_dict({**file_btn_style_attrs, "background-color": file_btn_original_bg_key})
        file_btn_pressed_style = self._get_pressed_style_from_normal(file_btn_normal_style, file_btn_original_bg_key)

        for btn_top in file_project_buttons:
            btn_top.setFixedHeight(32) 
            btn_top.setCustomStyles(file_btn_normal_style, file_btn_pressed_style)
            file_project_buttons_layout.addWidget(btn_top) 
        top_bar_layout.addWidget(file_project_buttons_widget, 0, 0, Qt.AlignLeft) 
        
        playback_button_stylesheet_for_checked = """
            CustomStyledButton:checked { 
                background-color: #2A2A2A !important; 
                border: 1px solid #50C878 !important; 
            }
             CustomStyledButton:checked:pressed { 
                background-color: #212121 !important; 
            }
        """
        
        playback_controls_widget = QWidget() 
        playback_controls_widget.setStyleSheet("background-color: #3d3d3d; border-radius: 5px; padding: 2px;") 
        playback_controls_layout = QHBoxLayout(playback_controls_widget) 
        playback_controls_layout.setContentsMargins(2,2,2,2) 
        playback_controls_layout.setSpacing(2) 

        for i, btn in enumerate(self.playback_buttons_group):
            current_style = btn.styleSheet() 
            btn.setStyleSheet(current_style + " " + playback_button_stylesheet_for_checked)
            playback_controls_layout.addWidget(btn) 
        top_bar_layout.addWidget(playback_controls_widget, 0, 1, Qt.AlignCenter) 

        self.filename_label = QLabel("현재 작업중 : 없음")
        self.filename_label.setStyleSheet("color: #AAAAAA; padding-left: 12px;") 
        top_bar_layout.addWidget(self.filename_label, 0, 2, Qt.AlignRight) 

        top_bar_layout.setColumnStretch(0, 1) 
        top_bar_layout.setColumnStretch(1, 0) 
        top_bar_layout.setColumnStretch(2, 1) 

        content_area_layout.addLayout(top_bar_layout) 

        common_scrollbar_style = """
            QScrollBar:horizontal {
                height: 8px; background-color: #111111; margin: 0px; border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #808080; min-width: 20px; border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover { background: #A0A0A0; }
            QScrollBar::handle:horizontal:pressed { background: #606060; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                background: none; border: none; width: 0px; height: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: #111111; }

            QScrollBar:vertical {
                width: 8px; background-color: #111111; margin: 0px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #808080; min-height: 20px; border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: #A0A0A0; }
            QScrollBar::handle:vertical:pressed { background: #606060; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none; border: none; width: 0px; height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #111111; }
        """

        self.timeline_layout = QHBoxLayout()
        self.timeline_layout.setSpacing(0)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.timeline_layout.setSizeConstraint(QLayout.SetFixedSize)
        self.timeline_widget = QWidget()
        self.timeline_widget.setLayout(self.timeline_layout)
        self.timeline_widget.setStyleSheet("background-color: #202020; padding-top: 5px;")
        self.timeline_widget.setMinimumHeight(36)
        self.timeline_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(False)
        self.timeline_scroll.setFixedHeight(36)
        self.timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.timeline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timeline_scroll.setWidget(self.timeline_widget)
        self.timeline_scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: #202020; }}
            QScrollArea::corner {{ background: #111111; }}
            QScrollArea > QWidget {{ background-color: #202020; }}
            {common_scrollbar_style}
        """)
        content_area_layout.addWidget(self.timeline_scroll)

        self.selected_frame_label = QLabel("선택 중인 프레임: -")
        self.selected_frame_label.setStyleSheet("padding: 4px;")

        self.motion_name_input = QLineEdit()
        self.motion_name_input.setPlaceholderText("모션 이름 입력")
        self.motion_name_input.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333; border-radius: 3px; padding: 5px;")

        self.primary_keyframe_btn = CustomStyledButton() 

        self.motion_list = CustomMotionListWidget(self) 
        self.motion_list.setStyleSheet(f"""
            QListWidget {{
                background-color: #111111;
                border: 1px solid #333;
                border-radius: 5px;
            }}
            QListWidget::item {{
                padding-top: 3px;     
                padding-bottom: 3px;  
                padding-left: 1px;    
                padding-right: 1px;   
            }}
            QListWidget::item:selected {{ background-color: #4A4A70; }}
            {common_scrollbar_style}
        """)
        self.motion_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.motion_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.motion_list.viewport().installEventFilter(self) 

        left_panel = QVBoxLayout()
        left_panel.addWidget(self.selected_frame_label)
        left_panel.addWidget(self.motion_name_input)
        left_panel.addWidget(self.primary_keyframe_btn)
        left_panel.addWidget(self.motion_list)

        center_panel_title_layout = QHBoxLayout() 
        self.frame_preview_label = QLabel("프레임 설명 미리보기 (시작 0F 기준)")
        center_panel_title_layout.addWidget(self.frame_preview_label)
        center_panel_title_layout.addStretch(1) 

        self.copy_desc_button = CustomStyledButton("내용 복사") 
        self.copy_desc_button.setFixedHeight(24) 
        desc_btn_style_attrs = {"color": "white", "border-radius": "3px", "padding": "0 8px"}
        desc_btn_normal_style = self._generate_style_str_from_dict({**desc_btn_style_attrs, "background-color": "#303030"})
        desc_btn_pressed_style = self._get_pressed_style_from_normal(desc_btn_normal_style, "#303030")
        self.copy_desc_button.setCustomStyles(desc_btn_normal_style, desc_btn_pressed_style)
        center_panel_title_layout.addWidget(self.copy_desc_button)

        self.frame_preview = QListWidget()
        self.frame_preview.setStyleSheet(f"""
            QListWidget {{
                background-color: #111111; color: white;
                border: 1px solid #333; border-radius: 5px;
            }}
            QListWidget::item {{ 
                padding-top: 1px;    
                padding-bottom: 1px; 
                padding-left: 1px;
                padding-right: 1px;
            }}
            {common_scrollbar_style}
        """)
        self.frame_preview.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.frame_preview.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection) 
        self.frame_preview.viewport().installEventFilter(self) 

        center_panel = QVBoxLayout()
        center_panel.addLayout(center_panel_title_layout) 
        center_panel.addWidget(self.frame_preview) 

        self.graphics_scene = QGraphicsScene(self)
        self.pixmap_item = QGraphicsPixmapItem() 
        self.graphics_scene.addItem(self.pixmap_item) 
        self.graphics_view = QGraphicsView(self.graphics_scene, self) 

        self.graphics_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.graphics_view.setStyleSheet("background-color: #000000; border: 1px solid gray; border-radius: 5px;")
        self.graphics_view.setRenderHint(QPainter.Antialiasing, True)
        self.graphics_view.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graphics_view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.graphics_view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.graphics_view.setContextMenuPolicy(Qt.CustomContextMenu)

        self.preview_button_container = QWidget(self.graphics_view) 
        preview_button_container_layout = QVBoxLayout(self.preview_button_container)
        preview_button_container_layout.setContentsMargins(2, 2, 2, 2) 
        preview_button_container_layout.setSpacing(2) 
        
        preview_button_container_layout.addWidget(self.preview_zoom_in_btn)
        preview_button_container_layout.addWidget(self.preview_zoom_out_btn)
        preview_button_container_layout.addWidget(self.preview_home_btn)
        preview_button_container_layout.addStretch() 

        self.preview_button_container.setStyleSheet("background-color: transparent; border: none;") 
        
        button_height_pv = 48 
        button_width_pv = 48
        spacing_pv = 2 
        margin_pv = 2 
        container_height = (button_height_pv * 2.25) + (spacing_pv * 2) + (margin_pv * 2) 
        container_width = button_width_pv + (margin_pv * 2) 
        self.preview_button_container.setFixedSize(container_width, container_height)
        
        self.preview_button_container.move(1, 1) 

        right_panel = QVBoxLayout()
        right_panel.addWidget(self.graphics_view) 

        middle_panel = QHBoxLayout()
        middle_panel.addLayout(left_panel, 2)
        middle_panel.addLayout(center_panel, 2)
        middle_panel.addLayout(right_panel, 6)
        content_area_layout.addLayout(middle_panel)
        content_area_layout.setStretchFactor(middle_panel, 1) 

        self.export_gif_btn = CustomStyledButton("애니샘플 출력하기 (GIFs)")
        self.export_txt_btn = CustomStyledButton("프레임설명 출력하기 (TXT)")
        self.export_all_btn = CustomStyledButton("모두 저장 (GIFs + TXT)")
        
        button_height = 47
        export_btn_original_bg_key = "#303030"
        export_btn_style_attrs = {"color": "white", "border-radius": "5px", "padding": "0 15px"}

        export_btn_normal_style = self._generate_style_str_from_dict({**export_btn_style_attrs, "background-color": export_btn_original_bg_key})
        export_btn_pressed_style = self._get_pressed_style_from_normal(export_btn_normal_style, export_btn_original_bg_key)

        for b_export in [self.export_gif_btn, self.export_txt_btn, self.export_all_btn]:
            b_export.setFixedHeight(button_height)
            b_export.setCustomStyles(export_btn_normal_style, export_btn_pressed_style)
            b_export.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 5, 0, 5)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.export_gif_btn)
        bottom_bar.addWidget(self.export_txt_btn)
        bottom_bar.addWidget(self.export_all_btn)
        content_area_layout.addLayout(bottom_bar)

        main_app_layout.addWidget(content_area_widget, 1)
        main_app_layout.addWidget(self.status_bar)

        self.setLayout(main_app_layout)

    def handle_frame_button_double_click(self, frame_index):
        if self.selected_index != frame_index:
            self.select_frame(frame_index)

        current_motion_name = "" 
        is_existing_keyframe = frame_index in self.keyframes 

        if is_existing_keyframe: 
            current_motion_name = self.keyframes[frame_index]
            dialog_title = "[키프레임 수정]"
            prompt_label = f"프레임 {frame_index + 1} ('{current_motion_name}')\n모션의 새 이름을 입력하세요:"
        else: 
            dialog_title = "[키프레임 등록]"
            prompt_label = f"프레임 {frame_index + 1}에\n새 모션 이름을 입력하세요:"

        new_name, ok = QInputDialog.getText(self, dialog_title, prompt_label, QLineEdit.EchoMode.Normal, current_motion_name)

        def delayed_style_reset_for_frame_button():
            if 0 <= frame_index < len(self.frame_buttons):
                button_instance = self.frame_buttons[frame_index]
                if isinstance(button_instance, FrameButton): 
                    self.update_frame_button_styles()
                    button_instance.update() 
        
        QTimer.singleShot(0, delayed_style_reset_for_frame_button) 
        
        if ok: 
            new_name_stripped = new_name.strip() 
            if not new_name_stripped: 
                QMessageBox.warning(self, "입력 오류", "모션 이름은 비워둘 수 없습니다.")
                return

            if is_existing_keyframe and new_name_stripped == current_motion_name:
                self._update_status(f"프레임 {frame_index + 1} ('{current_motion_name}') 모션 이름 변경 없음.", is_complete_success=True)
                return

            self.keyframes[frame_index] = new_name_stripped
            self.unsaved_changes = True 
            self.update_frame_button_styles() 
            self.refresh_motion_list()      
            self._update_primary_keyframe_button_ui() 

            if is_existing_keyframe: 
                self._update_status(f"프레임 {frame_index + 1}의 모션이 '{current_motion_name}'에서 '{new_name_stripped}'(으)로 수정됨.", is_complete_success=True)
            else: 
                self._update_status(f"프레임 {frame_index + 1}에 '{new_name_stripped}' 모션 신규 등록됨.", is_complete_success=True)
        else: 
            self._update_status(f"프레임 {frame_index + 1} 키프레임 등록/수정 취소됨.")

    def _update_status(self, message, is_loading=False, is_complete_success=False):
        self._status_timer.stop() 
        self.status_label.setText(message) 
        self._current_status_message_for_timer = message 

        current_style = ""
        if is_loading: 
            current_style = self.status_label_loading_style
        elif is_complete_success: 
            current_style = self.status_label_complete_style
            self._status_timer.start(1000) 
        else: 
            current_style = self.status_label_default_style

        self.status_label.setStyleSheet(current_style) 
        QApplication.processEvents() 

    def _clear_status_loading_style(self):
        self.status_label.setText(self._current_status_message_for_timer) 
        self.status_label.setStyleSheet(self.status_label_default_style) 
        QApplication.processEvents() 

    def connect_signals(self):
        self.new_project_btn.clicked.connect(lambda: self.start_new_project(show_message=True))
        self.load_btn.clicked.connect(self.load_gif_file)
        self.save_btn.clicked.connect(self.save_settings)
        self.load_cfg_btn.clicked.connect(self.load_settings)

        self.primary_keyframe_btn.clicked.connect(self._on_primary_keyframe_button_clicked)

        self.motion_list.itemPressed.connect(self.on_motion_list_item_pressed) 
        self.frame_preview.itemPressed.connect(self.on_frame_preview_item_pressed) 
        if hasattr(self, 'copy_desc_button'): 
            self.copy_desc_button.clicked.connect(self._copy_all_frame_descriptions_to_clipboard)

        self.export_gif_btn.clicked.connect(self.export_motion_segments)
        self.export_txt_btn.clicked.connect(self.export_frame_descriptions_to_txt)
        self.export_all_btn.clicked.connect(self.export_all_data)

        self.playback_timer.timeout.connect(self._advance_frame) 

        self.prev_btn.pressed.connect(partial(self._on_playback_button_pressed, self.prev_btn))
        self.prev_btn.released.connect(partial(self._on_playback_button_released, self.prev_btn))
        self.prev_btn.clicked.connect(self._on_prev_keyframe_clicked)

        self.play_pause_btn.toggled.connect(self._on_play_pause_toggled) 
        self.play_pause_btn.pressed.connect(partial(self._on_playback_button_pressed, self.play_pause_btn))
        self.play_pause_btn.released.connect(partial(self._on_playback_button_released, self.play_pause_btn))

        self.next_btn.pressed.connect(partial(self._on_playback_button_pressed, self.next_btn))
        self.next_btn.released.connect(partial(self._on_playback_button_released, self.next_btn))
        self.next_btn.clicked.connect(self._on_next_keyframe_clicked)

        self.loop_btn.toggled.connect(self._on_loop_toggled) 
        self.loop_btn.pressed.connect(partial(self._on_playback_button_pressed, self.loop_btn))
        self.loop_btn.released.connect(partial(self._on_playback_button_released, self.loop_btn))

        if self.preview_zoom_in_btn:
            self.preview_zoom_in_btn.clicked.connect(lambda: self._change_preview_scale(1)) 
        if self.preview_zoom_out_btn:
            self.preview_zoom_out_btn.clicked.connect(lambda: self._change_preview_scale(-1)) 
        if self.preview_home_btn:
            self.preview_home_btn.clicked.connect(self._reset_preview_view) 
        
        if self.graphics_view:
            self.graphics_view.customContextMenuRequested.connect(self._show_preview_context_menu)

    def _show_preview_context_menu(self, position):
        if not self.all_frame_data: 
            return

        menu = QMenu(self) 
        
        smooth_action = QAction("부드러운 필터 (Smooth)", self)
        smooth_action.setCheckable(True) 
        smooth_action.setChecked(self.current_transformation_mode == Qt.TransformationMode.SmoothTransformation)
        smooth_action.triggered.connect(lambda: self._set_preview_transformation_mode(Qt.TransformationMode.SmoothTransformation))
        menu.addAction(smooth_action)

        pixelated_action = QAction("픽셀 유지 필터 (Fast/Nearest)", self)
        pixelated_action.setCheckable(True)
        pixelated_action.setChecked(self.current_transformation_mode == Qt.TransformationMode.FastTransformation)
        pixelated_action.triggered.connect(lambda: self._set_preview_transformation_mode(Qt.TransformationMode.FastTransformation))
        menu.addAction(pixelated_action)
        
        menu.exec_(self.graphics_view.viewport().mapToGlobal(position)) 

    def on_motion_list_item_pressed(self, item):
        self.pressed_motion_list_item = item

    def on_frame_preview_item_pressed(self, item):
        self.pressed_frame_preview_item = item

    def _update_primary_keyframe_button_ui(self):
        if self.selected_index is not None and self.selected_index in self.keyframes:
            self.primary_keyframe_btn.setText("키프레임 해제/모션삭제")
            normal_style = self.remove_keyframe_style 
            pressed_style = self._get_pressed_style_from_normal(normal_style, "#F44336") 
            self.primary_keyframe_btn.setCustomStyles(normal_style, pressed_style)
        else:
            self.primary_keyframe_btn.setText("키프레임 설정/모션등록")
            normal_style = self.add_keyframe_style 
            pressed_style = self._get_pressed_style_from_normal(normal_style, "#4CAF50") 
            self.primary_keyframe_btn.setCustomStyles(normal_style, pressed_style)

    def _on_primary_keyframe_button_clicked(self):
        if self.selected_index is not None and self.selected_index in self.keyframes:
            self.remove_keyframe() 
        else:
            self.add_keyframe() 

    def _get_motion_segment_for_frame(self, frame_index):
        if not self.keyframes or frame_index is None:
            return None, None 

        sorted_keys = sorted(self.keyframes.keys()) 

        current_motion_start_key = None
        for k_start in sorted_keys:
            if k_start <= frame_index:
                current_motion_start_key = k_start
            else: 
                break

        if current_motion_start_key is None: 
            return None, None

        try:
            current_motion_start_key_idx_in_sorted = sorted_keys.index(current_motion_start_key)
            k_end = sorted_keys[current_motion_start_key_idx_in_sorted + 1] - 1 \
                if current_motion_start_key_idx_in_sorted + 1 < len(sorted_keys) \
                else len(self.all_frame_data) - 1
            
            if current_motion_start_key <= frame_index <= k_end:
                 return current_motion_start_key, k_end
            else: 
                 return None, None
        except ValueError: 
            return None, None

    def _get_current_motion_start_key(self, frame_index, sorted_keys):
        if not sorted_keys: 
            return None

        insert_point = bisect.bisect_right(sorted_keys, frame_index)

        if insert_point == 0: 
            if sorted_keys and sorted_keys[0] == frame_index:
                return sorted_keys[0]
            return None 

        current_motion_start = sorted_keys[insert_point - 1]

        start_key_idx_in_list = -1
        try:
            start_key_idx_in_list = sorted_keys.index(current_motion_start)
        except ValueError: 
            return None

        end_frame_of_current_motion = sorted_keys[start_key_idx_in_list + 1] - 1 \
            if start_key_idx_in_list + 1 < len(sorted_keys) \
            else len(self.all_frame_data) - 1

        if current_motion_start <= frame_index <= end_frame_of_current_motion:
            return current_motion_start
        else:
            if frame_index > end_frame_of_current_motion and \
               insert_point < len(sorted_keys) and \
               frame_index < sorted_keys[insert_point]: 
                return current_motion_start 
            elif sorted_keys and frame_index > sorted_keys[-1]: 
                return sorted_keys[-1] 
            return None 

    def _update_playback_context_and_resume(self, new_target_frame):
        self.current_playback_frame_index = new_target_frame 

        if not self.play_pause_btn.isChecked():
            self.play_pause_btn.setChecked(True) 
        self.play_pause_btn.setIcon(QIcon(self.play_pause_btn._icon_path_normal_on)) 

        status_msg = "" 

        if self.loop_btn.isChecked(): 
            start_motion, end_motion = self._get_motion_segment_for_frame(self.current_playback_frame_index)
            if start_motion is not None: 
                self.is_looping_specific_motion = True
                self.active_motion_start_index = start_motion
                self.active_motion_end_index = end_motion
                if not (self.active_motion_start_index <= self.current_playback_frame_index <= self.active_motion_end_index):
                    self.current_playback_frame_index = self.active_motion_start_index

                motion_name = self.keyframes.get(self.active_motion_start_index, "알 수 없는 모션")
                status_msg = f"'{motion_name}' ({self.active_motion_start_index+1}F) 모션 반복 재생 중..."
                self.play_pause_btn.setToolTip("일시정지 (모션 반복 중)")
            else: 
                self.is_looping_specific_motion = False 
                status_msg = f"전체 GIF 반복 재생 중... (현재 프레임 {self.current_playback_frame_index+1}F, 활성 모션 없음)"
                self.play_pause_btn.setToolTip("일시정지 (전체 반복 중)")
        else: 
            self.is_looping_specific_motion = False
            status_msg = f"전체 GIF 반복 재생 중... (현재 프레임 {self.current_playback_frame_index+1}F)"
            self.play_pause_btn.setToolTip("일시정지 (전체 반복 중)")

        self._update_status(status_msg, is_loading=True) 

        if 0 <= self.current_playback_frame_index < len(self.all_frame_data):
            delay = self.all_frame_data[self.current_playback_frame_index]['delay']
            if delay <= 0: delay = 100 
            self.playback_timer.start(delay) 
        else: 
            self._stop_playback_and_reset_ui()

    def _on_play_pause_toggled(self, checked):
        if not self.all_frame_data: 
            self.play_pause_btn.setChecked(False) 
            self._update_status("재생할 GIF 데이터가 없습니다.")
            return

        if checked: 
            if not (0 <= self.current_playback_frame_index < len(self.all_frame_data)):
                if self.selected_index is not None and 0 <= self.selected_index < len(self.all_frame_data):
                    self.current_playback_frame_index = self.selected_index 
                elif self.all_frame_data: 
                    self.current_playback_frame_index = 0 
                else: 
                    self.play_pause_btn.setChecked(False)
                    return

            self.select_frame(self.current_playback_frame_index, _internal_call_maintains_play_state=False) 
            
            self._update_playback_context_and_resume(self.current_playback_frame_index)
            self.play_pause_btn.setIcon(QIcon(self.play_pause_btn._icon_path_normal_on)) 
        else: 
            self.playback_timer.stop() 
            self.play_pause_btn.setIcon(QIcon(self.play_pause_btn._icon_path_normal_off)) 
            if self.loop_btn.isChecked(): 
                 self.play_pause_btn.setToolTip("현재 모션 반복 재생") 
            else: 
                 self.play_pause_btn.setToolTip("재생 (전체 반복)") 
            self._update_status("재생 일시정지됨.") 

    def _advance_frame(self):
        if not self.all_frame_data or self.current_playback_frame_index == -1: 
            self._stop_playback_and_reset_ui() 
            return

        next_frame_index = self.current_playback_frame_index + 1 

        if self.is_looping_specific_motion and self.loop_btn.isChecked(): 
            if next_frame_index > self.active_motion_end_index: 
                self.current_playback_frame_index = self.active_motion_start_index 
            else:
                self.current_playback_frame_index = next_frame_index 
        else: 
            if next_frame_index >= len(self.all_frame_data): 
                self.current_playback_frame_index = 0 
            else:
                self.current_playback_frame_index = next_frame_index 

        self.select_frame(self.current_playback_frame_index, _internal_call_maintains_play_state=True) 
        
        delay = self.all_frame_data[self.current_playback_frame_index]['delay']
        if delay <= 0: delay = 100 
        self.playback_timer.start(delay) 

    def _stop_playback_and_reset_ui(self):
        self.playback_timer.stop() 
        if self.play_pause_btn.isChecked(): 
            self.play_pause_btn.setChecked(False) 
        else: 
            self.play_pause_btn.setIcon(QIcon(self.play_pause_btn._icon_path_normal_off)) 
            if self.loop_btn.isChecked():
                 self.play_pause_btn.setToolTip("현재 모션 반복 재생")
            else:
                 self.play_pause_btn.setToolTip("재생 (전체 반복)")

    def _on_loop_toggled(self, checked):
        if checked: 
            self.loop_btn.setIcon(QIcon(self.loop_btn._icon_path_normal_on)) 
            self.loop_btn.setToolTip("현재 모션 반복 (활성화)") 
            self._update_status("모션 반복 활성화됨.")
            if self.playback_timer.isActive(): 
                self._update_playback_context_and_resume(self.current_playback_frame_index) 
            else: 
                 self.play_pause_btn.setToolTip("현재 모션 반복 재생") 

        else: 
            self.loop_btn.setIcon(QIcon(self.loop_btn._icon_path_normal_off)) 
            self.loop_btn.setToolTip("현재 모션 반복 (비활성화)") 
            self._update_status("모션 반복 비활성화됨.")
            self.is_looping_specific_motion = False 
            if self.playback_timer.isActive(): 
                self._update_playback_context_and_resume(self.current_playback_frame_index)
            else: 
                 self.play_pause_btn.setToolTip("재생 (전체 반복)") 

    def _on_prev_keyframe_clicked(self):
        if not self.all_frame_data or not self.keyframes: 
            self._update_status("등록된 키프레임이 없거나 GIF가 로드되지 않았습니다.")
            if self.playback_timer.isActive(): self._stop_playback_and_reset_ui() 
            return

        was_playing = self.playback_timer.isActive() 
        if was_playing: 
            self.playback_timer.stop()

        sorted_keys = sorted(self.keyframes.keys()) 
        current_selected_or_playback_idx = self.current_playback_frame_index if was_playing else \
                                           (self.selected_index if self.selected_index is not None else 0)

        current_motion_start_key = self._get_current_motion_start_key(current_selected_or_playback_idx, sorted_keys)

        new_target_frame = -1 
        target_motion_name = "알 수 없는 모션"

        if not sorted_keys: 
            if was_playing: self._stop_playback_and_reset_ui()
            self._update_status("등록된 키프레임이 없습니다.")
            return

        if current_motion_start_key is None : 
            new_target_frame = sorted_keys[-1] 
        else: 
            try:
                idx_in_sorted = sorted_keys.index(current_motion_start_key) 
                target_key_idx_in_sorted = idx_in_sorted - 1 
                if target_key_idx_in_sorted < 0: 
                    target_key_idx_in_sorted = len(sorted_keys) - 1 
                new_target_frame = sorted_keys[target_key_idx_in_sorted] 
            except ValueError: 
                 new_target_frame = sorted_keys[-1] 

        if new_target_frame != -1: 
            target_motion_name = self.keyframes.get(new_target_frame, "알 수 없는 모션")
            self.select_frame(new_target_frame, _internal_call_maintains_play_state=was_playing) 

            if was_playing: 
                self._update_playback_context_and_resume(new_target_frame) 
            else: 
                self._update_status(f"이전 모션 '{target_motion_name}' ({new_target_frame + 1}F)으로 이동.")
                self.current_playback_frame_index = new_target_frame 
        else: 
            if was_playing: self._stop_playback_and_reset_ui()
            self._update_status("이전 모션을 찾을 수 없습니다.")

    def _on_next_keyframe_clicked(self):
        if not self.all_frame_data or not self.keyframes:
            self._update_status("등록된 키프레임이 없거나 GIF가 로드되지 않았습니다.")
            if self.playback_timer.isActive(): self._stop_playback_and_reset_ui()
            return

        was_playing = self.playback_timer.isActive()
        if was_playing:
            self.playback_timer.stop()

        sorted_keys = sorted(self.keyframes.keys())
        current_selected_or_playback_idx = self.current_playback_frame_index if was_playing else \
                                           (self.selected_index if self.selected_index is not None else 0)

        current_motion_start_key = self._get_current_motion_start_key(current_selected_or_playback_idx, sorted_keys)

        new_target_frame = -1
        target_motion_name = "알 수 없는 모션"

        if not sorted_keys:
            if was_playing: self._stop_playback_and_reset_ui()
            self._update_status("등록된 키프레임이 없습니다.")
            return

        if current_motion_start_key is None: 
            new_target_frame = sorted_keys[0] 
        else:
            try:
                idx_in_sorted = sorted_keys.index(current_motion_start_key)
                target_key_idx_in_sorted = idx_in_sorted + 1 
                if target_key_idx_in_sorted >= len(sorted_keys): 
                    target_key_idx_in_sorted = 0 
                new_target_frame = sorted_keys[target_key_idx_in_sorted]
            except ValueError:
                new_target_frame = sorted_keys[0] 

        if new_target_frame != -1:
            target_motion_name = self.keyframes.get(new_target_frame, "알 수 없는 모션")
            self.select_frame(new_target_frame, _internal_call_maintains_play_state=was_playing)

            if was_playing:
                self._update_playback_context_and_resume(new_target_frame)
            else:
                self._update_status(f"다음 모션 '{target_motion_name}' ({new_target_frame + 1}F)으로 이동.")
                self.current_playback_frame_index = new_target_frame
        else:
            if was_playing: self._stop_playback_and_reset_ui()
            self._update_status("다음 모션을 찾을 수 없습니다.")

    def _on_playback_button_pressed(self, button):
        if button == self.play_pause_btn: 
            if button.isChecked(): 
                button.setIcon(QIcon(button._icon_path_pressed_on))
            else: 
                button.setIcon(QIcon(button._icon_path_pressed_off))
        elif button == self.loop_btn: 
            if button.isChecked(): 
                button.setIcon(QIcon(button._icon_path_pressed_on))
            else: 
                button.setIcon(QIcon(button._icon_path_pressed_off))
        elif hasattr(button, '_icon_path_pressed'): 
            button.setIcon(QIcon(button._icon_path_pressed))

    def _on_playback_button_released(self, button):
        if button == self.play_pause_btn:
            if button.isChecked(): 
                button.setIcon(QIcon(button._icon_path_normal_on))
            else: 
                button.setIcon(QIcon(button._icon_path_normal_off))
        elif button == self.loop_btn:
            if button.isChecked(): 
                button.setIcon(QIcon(button._icon_path_normal_on))
            else: 
                button.setIcon(QIcon(button._icon_path_normal_off))
        elif hasattr(button, '_icon_path_normal'): 
            button.setIcon(QIcon(button._icon_path_normal))

    def _apply_current_scale(self):
        if self.graphics_view and self.pixmap_item and not self.pixmap_item.pixmap().isNull():
            visible_rect_before = self.graphics_view.mapToScene(self.graphics_view.viewport().rect()).boundingRect()
            center_point_before = visible_rect_before.center()

            self.graphics_view.resetTransform() 
            self.graphics_view.scale(self.current_scale_factor, self.current_scale_factor) 
            
            if self.pixmap_item.pixmap() and not self.pixmap_item.pixmap().isNull() and self.pixmap_item.scene():
                current_center = self.pixmap_item.sceneBoundingRect().center()
                if not center_point_before.isNull() and self.graphics_view.dragMode() == QGraphicsView.ScrollHandDrag:
                    self.graphics_view.centerOn(center_point_before)
                else: 
                    self.graphics_view.centerOn(current_center)
            
            self._update_preview_button_states()

    def _change_preview_scale(self, delta_index):
        if not self.graphics_view or not self.all_frame_data: return 

        new_index = self.current_scale_index + delta_index 
        if 0 <= new_index < len(self.scale_levels): 
            if self.current_scale_index != new_index: 
                self.current_scale_index = new_index
                self.current_scale_factor = self.scale_levels[self.current_scale_index]
                self._apply_current_scale() 
                self._update_status(f"미리보기 배율: {self.current_scale_factor:.2f}x")
        elif new_index < 0: 
            self._update_status(f"최소 배율({self.scale_levels[0]:.2f}x)입니다.")
        else: 
            self._update_status(f"최대 배율({self.scale_levels[-1]:.2f}x)입니다.")
        self._update_preview_button_states() 

    def _set_preview_transformation_mode(self, mode):
        if self.current_transformation_mode != mode: 
            self.current_transformation_mode = mode
            if self.pixmap_item: 
                self.pixmap_item.setTransformationMode(self.current_transformation_mode) 
            
            if self.graphics_view: 
                if mode == Qt.TransformationMode.SmoothTransformation:
                    self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True) 
                else: 
                    self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False) 

            filter_name = "부드럽게" if mode == Qt.TransformationMode.SmoothTransformation else "픽셀 유지(빠르게)"
            self._update_status(f"미리보기 필터: {filter_name}")

    def _reset_preview_view(self):
        if not self.graphics_view or not self.pixmap_item or self.pixmap_item.pixmap().isNull():
            self._update_status("초기화할 미리보기 내용이 없습니다.")
            return

        try:
            self.current_scale_index = self.scale_levels.index(1.0)
        except ValueError: 
            self.current_scale_index = min(range(len(self.scale_levels)), key=lambda i: abs(self.scale_levels[i]-1.0))
        self.current_scale_factor = self.scale_levels[self.current_scale_index]

        self.graphics_view.resetTransform() 
        self.graphics_view.scale(self.current_scale_factor, self.current_scale_factor) 

        if self.pixmap_item and not self.pixmap_item.pixmap().isNull():
            self.graphics_view.centerOn(self.pixmap_item.sceneBoundingRect().center())
        
        self._update_status(f"미리보기 초기화됨 (배율: {self.current_scale_factor:.2f}x, 현재 필터 유지)")
        self._update_preview_button_states()

    def ensure_frame_visible(self, index):
        if self.frame_buttons and 0 <= index < len(self.frame_buttons):
            widget_to_show = self.frame_buttons[index] 
            self.timeline_scroll.ensureWidgetVisible(widget_to_show, 50, 0) 

    def _is_view_panned(self, tolerance=1e-5):
        if not self.graphics_view or not self.pixmap_item or self.pixmap_item.pixmap().isNull() or not self.pixmap_item.scene():
            return False

        view_center_scene_pos = self.graphics_view.mapToScene(self.graphics_view.viewport().rect().center())
        pixmap_center_scene_pos = self.pixmap_item.sceneBoundingRect().center()
        
        return not (math.isclose(view_center_scene_pos.x(), pixmap_center_scene_pos.x(), abs_tol=tolerance) and \
                    math.isclose(view_center_scene_pos.y(), pixmap_center_scene_pos.y(), abs_tol=tolerance))

    def _update_preview_button_states(self):
        if not all([self.preview_zoom_in_btn, self.preview_zoom_out_btn, self.preview_home_btn, self.preview_button_container]):
            return

        if not self.all_frame_data or not self.graphics_view:
            self.preview_zoom_in_btn.setEnabled(False)
            self.preview_zoom_out_btn.setEnabled(False)
            self.preview_home_btn.setEnabled(False)
            self.preview_button_container.setVisible(False)
            return
        
        self.preview_button_container.setVisible(True)

        can_zoom_in = self.current_scale_index < len(self.scale_levels) - 1
        self.preview_zoom_in_btn.setEnabled(can_zoom_in)

        can_zoom_out = self.current_scale_index > 0
        self.preview_zoom_out_btn.setEnabled(can_zoom_out)

        is_scaled_not_default = not math.isclose(self.current_scale_factor, 1.0, abs_tol=1e-9) 
        is_panned = False
        if self.pixmap_item and self.pixmap_item.pixmap() and not self.pixmap_item.pixmap().isNull() and self.pixmap_item.scene():
            is_panned = self._is_view_panned()
        
        can_go_home = is_scaled_not_default or is_panned
        self.preview_home_btn.setEnabled(can_go_home)

    def eventFilter(self, watched_object, event):
        if watched_object == self.graphics_view.viewport():
            if event.type() == QEvent.Type.Wheel:
                if self.all_frame_data: 
                    delta = event.angleDelta().y() 
                    if delta < 0: 
                        self._change_preview_scale(-1)
                    elif delta > 0: 
                        self._change_preview_scale(1)
                    return True 
                else:
                    return False 
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._update_preview_button_states() 
                return False 

        if watched_object == self:
            if event.type() == QEvent.Type.Wheel:
                widget_under_mouse = QApplication.widgetAt(event.globalPosition().toPoint())
                
                current_widget = widget_under_mouse
                is_graphics_view_child = False
                while current_widget:
                    if current_widget == self.graphics_view:
                        is_graphics_view_child = True
                        break
                    current_widget = current_widget.parent()
                
                if is_graphics_view_child:
                    return False 

                if isinstance(widget_under_mouse, QLineEdit) or \
                   (hasattr(widget_under_mouse, 'viewport') and
                    (widget_under_mouse.viewport() == self.motion_list.viewport() or
                     widget_under_mouse.viewport() == self.frame_preview.viewport() or
                     widget_under_mouse.viewport() == self.timeline_scroll.viewport())):
                    return super().eventFilter(watched_object, event)

                if self.all_frame_data:
                    current_idx = self.selected_index if self.selected_index is not None else 0
                    new_index = current_idx
                    delta = event.angleDelta().y()
                    if delta < 0: 
                        if current_idx < len(self.all_frame_data) - 1: new_index = current_idx + 1
                    elif delta > 0: 
                        if current_idx > 0: new_index = current_idx - 1
                    if new_index != current_idx: self.select_frame(new_index)
                    return True 

        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if watched_object == self.motion_list.viewport():
                    if self.pressed_motion_list_item:
                        released_item = self.motion_list.itemAt(event.position().toPoint())
                        if released_item == self.pressed_motion_list_item:
                            frame_index_data = released_item.data(Qt.UserRole)
                            if frame_index_data is not None:
                                try:
                                    frame_index = int(frame_index_data)
                                    if 0 <= frame_index < len(self.all_frame_data):
                                        self.select_frame(frame_index)
                                except ValueError:
                                    pass 
                        self.pressed_motion_list_item = None
                    return True 

                elif watched_object == self.frame_preview.viewport():
                    if self.pressed_frame_preview_item:
                        released_item = self.frame_preview.itemAt(event.position().toPoint())
                        if released_item == self.pressed_frame_preview_item:
                            frame_index_data = released_item.data(Qt.UserRole)
                            if frame_index_data is not None and frame_index_data != -1: 
                                try:
                                    frame_index = int(frame_index_data)
                                    if frame_index >= 0 and frame_index < len(self.all_frame_data):
                                        self.select_frame(frame_index)
                                except ValueError:
                                    pass
                        self.pressed_frame_preview_item = None
                    return True

        return super().eventFilter(watched_object, event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            if QApplication.focusWidget() == self.frame_preview:
                selected_items = self.frame_preview.selectedItems()
                if selected_items:
                    sorted_items = sorted(selected_items, key=lambda item: self.frame_preview.row(item))
                    clipboard_text = "\n".join([item.text() for item in sorted_items]) 
                    if clipboard_text:
                        QApplication.clipboard().setText(clipboard_text)
                        self._update_status(f"{len(sorted_items)}개 항목(헤더 포함) 설명 선택 복사 완료.", is_complete_success=True)
                    else:
                        self._update_status("선택된 설명이 없습니다.")
                else:
                    self._update_status("복사할 설명이 선택되지 않았습니다.")
                event.accept()
                return
        super().keyPressEvent(event)

    def _copy_all_frame_descriptions_to_clipboard(self):
        if not self.all_frame_data and not self.keyframes : 
             if self.frame_preview.count() == 0: 
                self._update_status("복사할 프레임 설명 데이터가 없습니다.")
                return

        all_text = []
        for i in range(self.frame_preview.count()):
            item = self.frame_preview.item(i)
            if item: 
                all_text.append(item.text())
        
        if all_text:
            QApplication.clipboard().setText("\n".join(all_text))
            self._update_status("프레임 설명 전체 내용(헤더 포함) 복사 완료.", is_complete_success=True)
        else:
            self._update_status("복사할 프레임 설명 내용이 없습니다.")


    def start_new_project(self, show_message=False): 
        if self.unsaved_changes: 
            reply = QMessageBox.question(self, "변경사항 저장",
                                         "저장되지 않은 변경사항이 있습니다. 저장하시겠습니까?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Save) 
            if reply == QMessageBox.StandardButton.Save:
                self.save_settings() 
                if self.unsaved_changes: return 
            elif reply == QMessageBox.StandardButton.Cancel: return 

        self._stop_playback_and_reset_ui() 
        self.gif_path = None
        self.keyframes.clear()
        self.clear_timeline(); self.frame_buttons.clear() 
        self.selected_index = None; self.unsaved_changes = False
        self.original_gif_info = {}; self.all_frame_data = []
        self.original_gif_palette_data = None
        if self.filename_label: self.filename_label.setText("현재 작업중 : 없음")
        self.selected_frame_label.setText("선택 중인 프레임: -")
        self.motion_name_input.clear()
        self.motion_list.clear(); self.frame_preview.clear()

        if self.pixmap_item:
            self.pixmap_item.setPixmap(QPixmap()) 
        
        try:
            self.current_scale_index = self.scale_levels.index(1.0) 
        except ValueError: 
            self.current_scale_index = 3 
        self.current_scale_factor = self.scale_levels[self.current_scale_index]
        
        if self.pixmap_item: 
             self.pixmap_item.setTransformationMode(self.current_transformation_mode)
        
        if self.graphics_view: 
            self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.current_transformation_mode == Qt.TransformationMode.SmoothTransformation)
            if self.pixmap_item: 
                self.graphics_view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        
        self._update_preview_button_states() 

        self._update_primary_keyframe_button_ui() 

        if hasattr(self, 'loop_btn') and self.loop_btn.isChecked(): 
            self.loop_btn.setChecked(False)
        elif hasattr(self, 'loop_btn'): 
            self.loop_btn.setIcon(QIcon(self.loop_btn._icon_path_normal_off))
            self.loop_btn.setToolTip("현재 모션 반복 (활성화 시)")

        self.is_looping_specific_motion = False
        self.active_motion_start_index = -1
        self.active_motion_end_index = -1
        self.current_playback_frame_index = -1 

        if show_message: 
            QMessageBox.information(self, "새 프로젝트", "새 프로젝트가 시작되었습니다.")
        self._update_status("작업 대기중.") 

    def load_project_file(self, proj_path, silent=False):
        if not os.path.exists(proj_path): 
            if not silent: 
                print(f"Project file not found: {proj_path}")
            return False
        try:
            with open(proj_path, 'r', encoding='utf-8') as f:
                project_data = json.load(f) 
            loaded_keyframes_str_keys = project_data.get("keyframes", {}) 
            self.keyframes = {int(k): v for k, v in loaded_keyframes_str_keys.items()}

            if not silent: 
                self.refresh_motion_list() 
                self.update_frame_button_styles() 
                self._update_primary_keyframe_button_ui() 
            return True 
        except json.JSONDecodeError as e: 
            if not silent:
                QMessageBox.critical(self, "프로젝트 로드 오류", f"프로젝트 파일 형식이 올바르지 않습니다 (JSON 오류).\n파일 내용을 확인해주세요:\n{proj_path}\n{e}")
            self.keyframes = {} 
            return False
        except ValueError as e: 
            if not silent:
                QMessageBox.critical(self, "프로젝트 로드 오류", f"프로젝트 파일 내 키프레임 번호가 잘못되었습니다.\n파일 내용을 확인해주세요:\n{proj_path}\n{e}")
            self.keyframes = {}
            return False
        except Exception as e: 
            if not silent:
                QMessageBox.critical(self, "프로젝트 로드 오류", f"프로젝트 파일 로드 중 알 수 없는 오류가 발생했습니다:\n{proj_path}\n{e}\n{traceback.format_exc()}")
            self.keyframes = {}
            return False

    def load_gif_file(self):
        if self.unsaved_changes: 
            reply = QMessageBox.question(self, "변경사항 저장", "저장되지 않은 변경사항이 있습니다. 현재 프로젝트를 저장하시겠습니까?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
            if reply == QMessageBox.StandardButton.Save:
                self.save_settings()
                if self.unsaved_changes: return 
            elif reply == QMessageBox.StandardButton.Cancel: return 

        path, _ = QFileDialog.getOpenFileName(self, "GIF 파일 열기", "", "GIF 파일 (*.gif)") 
        if path: 
            self.start_new_project(show_message=False) 

            self._update_status(f"'{os.path.basename(path)}' GIF 불러오는 중...", is_loading=True) 
            self.gif_path = path 
            if self.filename_label: self.filename_label.setText(f"현재 작업중 : {os.path.basename(path)}") 

            proj_loaded_successfully = False 
            try:
                img = Image.open(path) 
                self.original_gif_info = img.info.copy() 
                self.original_gif_palette_data = img.getpalette() if img.mode == 'P' and img.getpalette() else None

                for i, frame in enumerate(ImageSequence.Iterator(img)):
                    duration = frame.info.get("duration", 100) 
                    frame_copy = frame.copy(); frame_info = frame.info.copy() 
                    frame_palette = frame.getpalette() if frame.mode == 'P' and frame.getpalette() else None
                    self.all_frame_data.append({'image': frame_copy, 'delay': duration, 'info': frame_info, 'palette': frame_palette})

                    btn = FrameButton(str(i + 1), i) 
                    btn.setFixedSize(26, 26) 
                    
                    btn.clicked.connect(lambda checked=False, idx=i: self.select_frame(idx)) 
                    btn.doubleClickedWithIndex.connect(self.handle_frame_button_double_click) 

                    self.timeline_layout.addWidget(btn); self.frame_buttons.append(btn) 

                base_name = os.path.splitext(self.gif_path)[0] 
                proj_path = base_name + ".gifproj" 
                if self.load_project_file(proj_path, silent=True): 
                    proj_loaded_successfully = True
                self.unsaved_changes = False 

                if self.all_frame_data: 
                    self.select_frame(0) 
                    self._reset_preview_view() 
                else: 
                    self.refresh_motion_list() 
                    self.update_frame_button_styles() 
                
                self._update_primary_keyframe_button_ui()
                self._update_preview_button_states() 

                msg = f"'{os.path.basename(self.gif_path)}' GIF 불러오기 완료."
                if proj_loaded_successfully:
                    msg += " .gifproj 파일확인, 불러오기 완료."
                self._update_status(msg, is_complete_success=True) 

            except Exception as e: 
                QMessageBox.critical(self, "GIF 로드 오류", f"GIF 파일을 여는 중 오류가 발생했습니다: {e}\n{traceback.format_exc()}")
                self._update_status("GIF 로드 실패.")
                self.start_new_project(show_message=False) 
        else: 
            self._update_status("GIF 불러오기 취소됨.")
            self._update_preview_button_states() 

    def _actual_save_settings(self, save_path):
        self._update_status(f"'{os.path.basename(save_path)}' 설정 파일 저장 중...", is_loading=True)
        serializable_keyframes = {str(k): v for k, v in self.keyframes.items()}
        project_data = {"gif_path": os.path.basename(self.gif_path) if self.gif_path else "", 
                        "keyframes": serializable_keyframes} 
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False) 
            self.unsaved_changes = False 
            self._update_status(f"'{os.path.basename(save_path)}' 파일 저장완료.", is_complete_success=True)
            return True 
        except Exception as e: 
            QMessageBox.critical(self, "저장 오류", f"설정 저장 중 오류가 발생했습니다:\n{e}\n{traceback.format_exc()}")
            self._update_status(f"'{os.path.basename(save_path)}' 파일 저장 실패.")
            return False 

    def save_settings(self):
        if not self.gif_path: 
            QMessageBox.warning(self, "저장 오류", "먼저 GIF 파일을 불러와주세요.")
            return

        default_proj_filename = os.path.splitext(os.path.basename(self.gif_path))[0] + ".gifproj"
        default_proj_dir = os.path.dirname(self.gif_path)
        default_proj_path = os.path.join(default_proj_dir, default_proj_filename)

        if os.path.exists(default_proj_path): 
            msg_box = QMessageBox(self) 
            msg_box.setWindowTitle("덮어쓰기 확인")
            msg_box.setText(f"'{default_proj_filename}' 파일이 이미 존재합니다. 설정을 덮어쓰시겠습니까?")
            msg_box.setIcon(QMessageBox.Icon.Question)

            overwrite_button = msg_box.addButton("예 (덮어쓰기)", QMessageBox.ButtonRole.YesRole)
            save_as_button = msg_box.addButton("다른 이름으로 저장", QMessageBox.ButtonRole.NoRole)
            cancel_button = msg_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec() 

            if msg_box.clickedButton() == overwrite_button: 
                if self._actual_save_settings(default_proj_path): 
                    QMessageBox.information(self, "설정 저장", f"설정이 성공적으로 덮어쓰기 되었습니다:\n{default_proj_path}")
            elif msg_box.clickedButton() == save_as_button: 
                self.save_settings_as()
            else: 
                self._update_status("설정 저장 취소됨.")
        else: 
            if self._actual_save_settings(default_proj_path):
                 QMessageBox.information(self, "설정 저장", f"설정이 성공적으로 저장되었습니다:\n{default_proj_path}")

    def save_settings_as(self):
        if not self.gif_path:
            QMessageBox.warning(self, "저장 오류", "먼저 GIF 파일을 불러와주세요.")
            return

        default_filename = os.path.splitext(os.path.basename(self.gif_path))[0] + ".gifproj"
        suggested_path = os.path.join(os.path.dirname(self.gif_path) if self.gif_path else "", default_filename)

        new_path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 설정 저장", suggested_path, "GIF 프로젝트 파일 (*.gifproj)") 

        if new_path: 
            if self._actual_save_settings(new_path): 
                 QMessageBox.information(self, "설정 저장", f"설정이 성공적으로 저장되었습니다:\n{new_path}")
        else: 
            self._update_status("다른 이름으로 설정 저장 취소됨.")

    def load_settings(self):
        if self.unsaved_changes: 
            reply = QMessageBox.question(self, "변경사항 저장", "저장되지 않은 변경사항이 있습니다. 현재 프로젝트를 저장하시겠습니까?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
            if reply == QMessageBox.StandardButton.Save: self.save_settings();
            if self.unsaved_changes: return 
            elif reply == QMessageBox.StandardButton.Cancel: return 

        path, _ = QFileDialog.getOpenFileName(self, "프로젝트 파일 열기", "", "GIF 프로젝트 파일 (*.gifproj)") 
        if not path: 
            self._update_status("설정 불러오기 취소됨.")
            return

        self._update_status(f"'{os.path.basename(path)}' 설정 파일 불러오는 중...", is_loading=True)
        proj_gif_name_in_file = None 
        try:
            with open(path, 'r', encoding='utf-8') as f: temp_project_data = json.load(f)
            proj_gif_name_in_file = temp_project_data.get("gif_path")
        except Exception as e: 
            QMessageBox.critical(self, "파일 읽기 오류", f"선택된 프로젝트 파일을 읽을 수 없습니다:\n{path}\n{e}");
            self._update_status("설정 파일 읽기 오류.")
            return

        if self.gif_path: 
            current_gif_name = os.path.basename(self.gif_path)
            if proj_gif_name_in_file and current_gif_name != proj_gif_name_in_file: 
                reply = QMessageBox.question(self, "경고: GIF 불일치", f"현재 GIF '{current_gif_name}'과 프로젝트의 GIF '{proj_gif_name_in_file}'이 다릅니다.\n계속 로드하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No: 
                    self._update_status("설정 불러오기 취소됨 (GIF 불일치).")
                    return
        elif proj_gif_name_in_file : 
             QMessageBox.warning(self, "GIF 없음", f"프로젝트 파일은 '{proj_gif_name_in_file}' GIF에 대한 설정입니다.\n먼저 해당 GIF 파일을 로드하거나, 현재 설정이 덮어씌워질 수 있음을 유의하세요.")
        else: 
            QMessageBox.warning(self, "로드 주의", "GIF 파일이 로드되지 않았습니다. 로드하는 설정이 현재 작업과 맞는지 확인해주세요.")

        if self.load_project_file(path): 
            self.refresh_motion_list(); self.update_frame_button_styles()
            self._update_primary_keyframe_button_ui()
            QMessageBox.information(self, "설정 불러오기", f"프로젝트 설정을 성공적으로 불러왔습니다:\n{path}")
            self.unsaved_changes = False 
            self._update_status(f"'{os.path.basename(path)}' .gifproj 파일 로드 완료.", is_complete_success=True)
        else: 
            self._update_status("설정 불러오기 실패.")
        self._update_preview_button_states() 

    def export_motion_segments(self):
        if not self.gif_path or not self.all_frame_data: QMessageBox.warning(self, "출력 오류", "먼저 GIF 파일을 불러와주세요."); self._update_status("애니샘플 출력 오류: GIF 없음."); return
        if not self.keyframes: QMessageBox.warning(self, "출력 오류", "모션(키프레임)이 등록되지 않았습니다."); self._update_status("애니샘플 출력 오류: 키프레임 없음."); return

        output_dir_dialog = QFileDialog(self, "모션 GIF 저장 폴더 선택", os.path.dirname(self.gif_path) if self.gif_path else "")
        output_dir_dialog.setFileMode(QFileDialog.FileMode.Directory); output_dir_dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if not output_dir_dialog.exec(): 
            self._update_status("애니샘플 출력 취소됨.")
            return
        output_dir = output_dir_dialog.selectedFiles()[0] 

        self._update_status("애니샘플 출력 중...", is_loading=True)
        exported_count, first_exported_basename = self._perform_gif_export(output_dir) 

        base_name = os.path.basename(self.gif_path) if self.gif_path else "알 수 없는 파일"
        original_file_base_name_no_ext = os.path.splitext(base_name)[0]

        if exported_count > 0: 
            others_count = exported_count - 1
            if exported_count == 1:
                msg = f"'{original_file_base_name_no_ext}'의 애니샘플 1종 저장 완료: {first_exported_basename}"
            else:
                msg = f"'{original_file_base_name_no_ext}'의 애니샘플 {exported_count}종 저장 완료. {first_exported_basename} 외 {others_count}종"
            self._update_status(msg, is_complete_success=True)
        elif hasattr(self, '_called_from_export_all') and self._called_from_export_all and exported_count == 0:
            pass
        elif exported_count == 0 and not (hasattr(self, '_called_from_export_all') and self._called_from_export_all):
             self._update_status(f"'{original_file_base_name_no_ext}'의 애니샘플 출력 실패 또는 생성된 파일 없음.")

    def _perform_gif_export(self, output_dir):
        if not self.gif_path or not self.all_frame_data or not self.keyframes:
            print("GIF export prerequisites not met in _perform_gif_export.") 
            if hasattr(self, '_called_from_export_all') and self._called_from_export_all:
                 if hasattr(self, '_export_all_errors'): self._export_all_errors.append("GIFs: 전제조건 미충족")
            else: 
                self._update_status("GIF 출력 오류: 전제조건 미충족")
            return 0, None 

        exported_count = 0 
        exported_basenames = [] 
        first_exported_name = None 
        try:
            sorted_keys = sorted(self.keyframes.keys()) 
            loop_count = self.original_gif_info.get('loop', 0) 
            original_global_background_idx = self.original_gif_info.get('background', None) 
            original_file_base_name_no_ext = os.path.splitext(os.path.basename(self.gif_path))[0] 

            for i, start_frame_idx in enumerate(sorted_keys):
                end_frame_idx = sorted_keys[i+1] - 1 if i+1 < len(sorted_keys) else len(self.all_frame_data) - 1
                motion_name = self.keyframes[start_frame_idx] 
                safe_motion_name = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in motion_name).rstrip()
                output_filename = f"{original_file_base_name_no_ext}_{start_frame_idx+1:02d}-{end_frame_idx+1:02d}_{safe_motion_name}.gif"
                output_path = os.path.join(output_dir, output_filename) 

                segment_frames_for_save = []; segment_delays_for_save = [] 
                for frame_idx_in_loop in range(start_frame_idx, end_frame_idx + 1):
                    if not (0 <= frame_idx_in_loop < len(self.all_frame_data)): continue 
                    original_frame_dict = self.all_frame_data[frame_idx_in_loop] 
                    frame_to_save = original_frame_dict['image'].copy() 
                    frame_to_save.info = original_frame_dict['info'].copy() 
                    segment_frames_for_save.append(frame_to_save)
                    segment_delays_for_save.append(original_frame_dict['delay'])

                if not segment_frames_for_save: continue 

                first_frame_to_save = segment_frames_for_save[0]
                save_options = {
                    'save_all': True, 'append_images': segment_frames_for_save[1:], 
                    'duration': segment_delays_for_save, 'loop': loop_count, 'optimize': False, 
                }
                if original_global_background_idx is not None: save_options['background'] = original_global_background_idx
                first_frame_to_save.save(output_path, **save_options) 
                exported_count += 1
                exported_basenames.append(os.path.basename(output_path))

            first_exported_name = exported_basenames[0] if exported_basenames else None 
            if exported_count > 0 and not hasattr(self, '_called_from_export_all'):
                QMessageBox.information(self, "모션 GIF 출력 완료", f"{exported_count}개의 모션 GIF 파일이 성공적으로 저장되었습니다.")
            elif exported_count == 0 and not hasattr(self, '_called_from_export_all'): 
                 QMessageBox.warning(self, "모션 GIF 출력 실패", "생성된 모션 GIF 파일이 없습니다.")
            return exported_count, first_exported_name 
        except Exception as e: 
            error_msg = f"GIFs: {str(e)}"
            if not hasattr(self, '_called_from_export_all'): 
                QMessageBox.critical(self, "GIF 출력 오류", f"모션 GIF 출력 중 오류 발생:\n{e}\n{traceback.format_exc()}")
                self._update_status("애니샘플 GIF 출력 중 오류 발생.")
            else: 
                if hasattr(self, '_export_all_errors'): self._export_all_errors.append(error_msg)
            print(f"Unexpected error during GIF export: {e}\n{traceback.format_exc()}") 
            return 0, None 

    def export_frame_descriptions_to_txt(self):
        if not self.gif_path or not self.all_frame_data: QMessageBox.warning(self, "출력 오류", "먼저 GIF 파일을 불러와주세요."); self._update_status("프레임 설명 출력 오류: GIF 없음."); return

        original_file_base_name_no_ext = os.path.splitext(os.path.basename(self.gif_path))[0]
        default_txt_filename = f"{original_file_base_name_no_ext}_프레임설명.txt"
        suggested_dir = os.path.dirname(self.gif_path) if self.gif_path else ""
        output_path, _ = QFileDialog.getSaveFileName(self, "프레임 설명 저장", os.path.join(suggested_dir, default_txt_filename), "Text Files (*.txt)") 
        if not output_path: 
            self._update_status("프레임 설명 출력 취소됨.")
            return

        self._update_status("프레임 설명 TXT 파일 저장 중...", is_loading=True)
        if self._perform_txt_export(output_path): 
            txt_filename = os.path.basename(output_path)
            self._update_status(f"'{original_file_base_name_no_ext}'의 프레임설명 저장 완료: {txt_filename}", is_complete_success=True)

    def _perform_txt_export(self, output_path):
        if not self.gif_path or not self.all_frame_data:
            print("TXT export prerequisites not met in _perform_txt_export.")
            if hasattr(self, '_called_from_export_all') and self._called_from_export_all:
                if hasattr(self, '_export_all_errors'): self._export_all_errors.append("TXT: 전제조건 미충족")
            else:
                self._update_status("TXT 출력 오류: 전제조건 미충족")
            return False

        try:
            content = [] 
            if not self.keyframes: 
                content.append("--- 전체 프레임 데이터 (키프레임 없음) ---")
                if not self.all_frame_data: content.append("(로드된 프레임 데이터가 없습니다)")
                for idx, frame_data in enumerate(self.all_frame_data):
                    delay = frame_data['delay']
                    content.append(f"{self._format_frame_number(idx)} : {delay}ms") 
            else: 
                sorted_keys = sorted(self.keyframes.keys())
                for i, start_frame_idx in enumerate(sorted_keys):
                    end_frame_idx = sorted_keys[i+1] - 1 if i+1 < len(sorted_keys) else len(self.all_frame_data)-1
                    motion_name = self.keyframes[start_frame_idx]
                    content.append(f"--- {motion_name} ({self._format_frame_number(start_frame_idx)} ~ {self._format_frame_number(end_frame_idx)}) ---") 
                    for frame_idx_in_segment in range(start_frame_idx, end_frame_idx + 1):
                        if 0 <= frame_idx_in_segment < len(self.all_frame_data):
                            delay = self.all_frame_data[frame_idx_in_segment]['delay']
                            content.append(f"{self._format_frame_number(frame_idx_in_segment)} : {delay}ms") 
                    content.append("") 
            with open(output_path, 'w', encoding='utf-8') as f: f.write("\n".join(content)) 

            if not hasattr(self, '_called_from_export_all'):
                QMessageBox.information(self, "프레임 설명 출력 완료", f"프레임 설명이 성공적으로 저장되었습니다:\n{output_path}")
            return True 
        except Exception as e: 
            error_msg = f"TXT: {str(e)}"
            if not hasattr(self, '_called_from_export_all'):
                QMessageBox.critical(self, "TXT 출력 오류", f"프레임 설명 파일 저장 중 오류 발생:\n{e}\n{traceback.format_exc()}")
                self._update_status("프레임 설명 TXT 파일 저장 중 오류 발생.")
            else:
                if hasattr(self, '_export_all_errors'): self._export_all_errors.append(error_msg)
            print(f"Error during TXT export: {e}\n{traceback.format_exc()}")
            return False 

    def export_all_data(self):
        if not self.gif_path or not self.all_frame_data: QMessageBox.warning(self, "출력 오류", "먼저 GIF 파일을 불러와주세요."); self._update_status("일괄 저장 오류: GIF 없음."); return

        output_dir_dialog = QFileDialog(self, "모든 데이터 저장 폴더 선택", os.path.dirname(self.gif_path) if self.gif_path else "")
        output_dir_dialog.setFileMode(QFileDialog.FileMode.Directory); output_dir_dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if not output_dir_dialog.exec():
            self._update_status("일괄 저장 취소됨.")
            return
        output_dir = output_dir_dialog.selectedFiles()[0]

        self._update_status("모든 데이터 일괄 저장 중...", is_loading=True)
        self._called_from_export_all = True 
        self._export_all_errors = [] 

        gif_exported_count = 0
        first_exported_gif_basename = None
        if self.keyframes:
            gif_exported_count, first_exported_gif_basename = self._perform_gif_export(output_dir)
        elif self.all_frame_data: 
             QMessageBox.information(self, "GIF 출력 알림", "키프레임이 없어 GIF 파일은 출력되지 않습니다. 프레임 설명만 출력됩니다.")

        original_file_base_name_no_ext = os.path.splitext(os.path.basename(self.gif_path))[0]
        default_txt_filename = f"{original_file_base_name_no_ext}_프레임설명.txt"
        output_txt_path = os.path.join(output_dir, default_txt_filename)
        txt_exported_success = self._perform_txt_export(output_txt_path)

        del self._called_from_export_all 

        status_msg_parts = []
        if gif_exported_count > 0:
            others_count = gif_exported_count - 1
            if gif_exported_count == 1:
                status_msg_parts.append(f"애니샘플 1종 ({first_exported_gif_basename})")
            else:
                status_msg_parts.append(f"애니샘플 {gif_exported_count}종 ({first_exported_gif_basename} 외 {others_count}종)")
        if txt_exported_success:
            status_msg_parts.append(f"프레임설명 ({os.path.basename(output_txt_path)})")

        final_status_msg = ""
        if status_msg_parts: 
            final_status_msg = f"'{original_file_base_name_no_ext}'의 " + " 및 ".join(status_msg_parts) + " 저장 완료."
        else: 
            final_status_msg = f"'{original_file_base_name_no_ext}' 관련 파일 저장 결과 없음."

        if self._export_all_errors: 
            error_details = "; ".join(self._export_all_errors)
            final_status_msg += f" (일부 오류: {error_details})"
            if self._export_all_errors and (gif_exported_count > 0 or txt_exported_success):
                 QMessageBox.warning(self, "일부 출력 오류", f"일괄 저장 중 일부 파일 처리 중 다음 오류 발생:\n" + "\n".join(self._export_all_errors))
            elif self._export_all_errors:
                 QMessageBox.critical(self, "전체 출력 오류", f"일괄 저장 중 다음 오류로 인해 파일이 저장되지 않았습니다:\n" + "\n".join(self._export_all_errors))

        self._update_status(final_status_msg, is_complete_success=(not self._export_all_errors and (gif_exported_count > 0 or txt_exported_success)))

        if not self._export_all_errors and (gif_exported_count > 0 or txt_exported_success): 
            QMessageBox.information(self, "모두 저장 완료", "선택한 폴더에 파일들이 저장되었습니다.\n" + final_status_msg.replace(". ", ".\n"))
        elif not self._export_all_errors and not gif_exported_count and not txt_exported_success: 
             QMessageBox.warning(self, "출력 결과", "키프레임이 없거나 데이터가 없어 저장된 파일이 없습니다.")

        if hasattr(self, '_export_all_errors'): 
            del self._export_all_errors

    def select_frame(self, index, _internal_call_maintains_play_state=False):
        if not (0 <= index < len(self.all_frame_data)): 
            return

        if self.playback_timer.isActive() and not _internal_call_maintains_play_state:
            self._stop_playback_and_reset_ui()

        pil_frame_to_display = self.all_frame_data[index]['image']

        if pil_frame_to_display.mode == 'P':
            pil_frame_to_display = pil_frame_to_display.convert("RGBA") if 'transparency' in self.all_frame_data[index]['info'] else pil_frame_to_display.convert("RGB").convert("RGBA")
        else: 
            pil_frame_to_display = pil_frame_to_display.convert("RGBA")

        data = pil_frame_to_display.tobytes("raw", "RGBA") 
        qimg = QImage(data, pil_frame_to_display.width, pil_frame_to_display.height, QImage.Format.Format_RGBA8888) 
        frame_pixmap = QPixmap.fromImage(qimg) 

        if self.pixmap_item:
            self.pixmap_item.setPixmap(frame_pixmap) 
            self.pixmap_item.setTransformationMode(self.current_transformation_mode) 

            if not frame_pixmap.isNull() and self.graphics_view:
                if not _internal_call_maintains_play_state : 
                    self._apply_current_scale() 
                else: 
                    self._update_preview_button_states()

        self.selected_index = index
        self.selected_frame_label.setText(f"선택 중인 프레임: {index + 1} ({self.all_frame_data[index]['delay']}ms)")
        self.update_frame_button_styles() 
        self._update_primary_keyframe_button_ui() 
        self.refresh_motion_list() 

        if not self.playback_timer.isActive():
            self.current_playback_frame_index = index

        if self.selected_index is not None:
            self.ensure_frame_visible(self.selected_index)

    def update_frame_button_styles(self):
        sorted_keys = sorted(self.keyframes.keys()) 
        for i, btn in enumerate(self.frame_buttons): 
            is_keyframe = i in self.keyframes 
            is_selected = (i == self.selected_index) 
            
            current_style_dict = {"padding": "0px", "margin": "0px"} 

            if is_selected: 
                current_style_dict["background-color"] = "#FFFFFF" 
                current_style_dict["color"] = "black" 
                current_style_dict["border"] = "2px solid #ffffff" 
                if is_keyframe: 
                    current_style_dict["border"] = "2px solid orange"
            elif is_keyframe: 
                current_style_dict["background-color"] = "#202020"
                current_style_dict["color"] = "white"
                current_style_dict["border"] = "2px solid orange"
            else: 
                in_motion_segment = False
                for k_idx, start_frame in enumerate(sorted_keys):
                    if start_frame <= i: 
                        if k_idx + 1 < len(sorted_keys): end_frame = sorted_keys[k_idx + 1] - 1
                        else: end_frame = len(self.all_frame_data) - 1
                        if i <= end_frame: in_motion_segment = True; break
                
                current_style_dict["color"] = "white"
                current_style_dict["border"] = "1px solid rgba(0, 0, 0, 0.5)"
                if in_motion_segment: 
                    current_style_dict["background-color"] = "#353535"
                else: 
                    current_style_dict["background-color"] = "#404040"
            
            normal_style_str = self._generate_style_str_from_dict(current_style_dict)
            btn.setStyleSheet(normal_style_str)

    def add_keyframe(self):
        name = self.motion_name_input.text().strip() 
        if not name: QMessageBox.warning(self, "모션 이름 없음", "모션 이름을 입력해주세요."); return
        if self.selected_index is None: QMessageBox.warning(self, "프레임 선택 오류", "먼저 프레임을 선택해주세요."); return

        self.keyframes[self.selected_index] = name 
        self.motion_name_input.clear(); 
        self.update_frame_button_styles() 
        self.refresh_motion_list(); self.unsaved_changes = True 
        self._update_primary_keyframe_button_ui() 
        self._update_status(f"프레임 {self.selected_index + 1}에 '{name}' 모션 등록 완료.", is_complete_success=True)

    def remove_keyframe(self):
        if self.selected_index is not None and self.selected_index in self.keyframes:
            removed_motion_name = self.keyframes[self.selected_index] 
            del self.keyframes[self.selected_index] 
            self.update_frame_button_styles() 
            self.refresh_motion_list(); self.unsaved_changes = True
            self._update_primary_keyframe_button_ui()
            self._update_status(f"프레임 {self.selected_index + 1}의 '{removed_motion_name}' 키프레임 해제 완료.", is_complete_success=True)

    def edit_motion_name(self, item):
        if not item: return

        start_frame_internal_data = item.data(Qt.UserRole)
        if start_frame_internal_data is None: 
            return

        try:
            start_frame_internal = int(start_frame_internal_data) 
        except ValueError: 
            print(f"오류: 모션 아이템의 UserRole 데이터가 유효한 정수가 아닙니다: {start_frame_internal_data}")
            return

        if start_frame_internal not in self.keyframes:
            selected_row = self.motion_list.row(item) 
            if selected_row < 0: return 
            sorted_keys = sorted(self.keyframes.keys()) 
            if selected_row >= len(sorted_keys): return 
            start_frame_internal = sorted_keys[selected_row] 
            if start_frame_internal not in self.keyframes: 
                QMessageBox.warning(self, "데이터 오류", "선택된 모션의 내부 데이터를 찾을 수 없습니다.")
                return

        current_name = self.keyframes.get(start_frame_internal) 

        if current_name is None: 
            print(f"오류: 프레임 인덱스 {start_frame_internal}에 해당하는 모션 이름이 None입니다.")
            return

        new_name, ok = QInputDialog.getText(self, "모션 이름 수정", "새 모션 이름을 입력하세요:", QLineEdit.EchoMode.Normal, current_name)
        if ok and new_name.strip() and new_name.strip() != current_name: 
            self.keyframes[start_frame_internal] = new_name.strip() 
            self.refresh_motion_list(); self.unsaved_changes = True 
            self._update_status(f"모션 '{current_name}'이(가) '{new_name.strip()}'(으)로 수정됨.", is_complete_success=True)
        elif ok and not new_name.strip(): 
            QMessageBox.warning(self, "입력 오류", "모션 이름은 비워둘 수 없습니다.")

    def _sync_motion_list_selection(self):
        for i in range(self.motion_list.count()):
            item = self.motion_list.item(i)
            if item:
                widget = self.motion_list.itemWidget(item)
                if isinstance(widget, QLabel): 
                    font = widget.font()
                    font.setBold(False) 
                    widget.setFont(font)

        if not self.keyframes or self.selected_index is None or self.motion_list.count() == 0:
            self.motion_list.setCurrentRow(-1) 
            return

        sorted_key_indices = sorted(self.keyframes.keys()) 
        target_item_index_in_list = -1 

        for motion_idx, key_start_frame in enumerate(sorted_key_indices):
            key_end_frame = sorted_key_indices[motion_idx + 1] - 1 if motion_idx + 1 < len(sorted_key_indices) else len(self.all_frame_data) - 1
            if key_start_frame <= self.selected_index <= key_end_frame: 
                target_item_index_in_list = motion_idx 
                break

        if target_item_index_in_list != -1: 
            self.motion_list.setCurrentRow(target_item_index_in_list) 
            current_item = self.motion_list.item(target_item_index_in_list)
            if current_item: 
                widget = self.motion_list.itemWidget(current_item)
                if isinstance(widget, QLabel):
                    font = widget.font()
                    font.setBold(True)
                    widget.setFont(font)
        else: 
            self.motion_list.setCurrentRow(-1)

    def refresh_motion_list(self):
        self.motion_list.clear() 
        self.frame_preview.clear()
        if not self.all_frame_data: return 

        keyframe_color_code = "#FFA500" 
        default_text_color_code = "#FFFFFF" 
        item_vertical_padding = 2 
        preview_item_height_reduction_factor = 0.75 

        if not self.keyframes: 
            header_item = QListWidgetItem(f"--- 전체 프레임 ({len(self.all_frame_data)}개) ---")
            header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter); header_item.setForeground(QColor("#FFA07A")) 
            header_item.setData(Qt.UserRole, -1) 
            self.frame_preview.addItem(header_item)

            font_metrics = QFontMetrics(self.frame_preview.font())
            header_height = int((font_metrics.height() + item_vertical_padding) * preview_item_height_reduction_factor)
            if header_height < font_metrics.height(): header_height = font_metrics.height() 
            header_item.setSizeHint(QSize(self.frame_preview.width() - 20, header_height)) 

            for idx, frame_data in enumerate(self.all_frame_data):
                delay = frame_data['delay']
                frame_desc = f"{self._format_frame_number(idx)} : {delay}ms"
                frame_item = QListWidgetItem(frame_desc)
                frame_item.setData(Qt.UserRole, idx) 
                if self.selected_index == idx : frame_item.setForeground(QColor("cyan")) 
                self.frame_preview.addItem(frame_item)
                
                current_item_height = int((font_metrics.height() + item_vertical_padding) * preview_item_height_reduction_factor)
                if current_item_height < font_metrics.height(): current_item_height = font_metrics.height()
                frame_item.setSizeHint(QSize(frame_item.sizeHint().width(), current_item_height))

            self._sync_motion_list_selection() 
            return 

        sorted_keys = sorted(self.keyframes.keys()) 
        font_metrics_motion = QFontMetrics(self.motion_list.font()) 
        font_metrics_preview = QFontMetrics(self.frame_preview.font()) 

        for i, start_frame_idx in enumerate(sorted_keys):
            end_frame_idx = sorted_keys[i+1] - 1 if i+1 < len(sorted_keys) else len(self.all_frame_data)-1
            motion_name = self.keyframes[start_frame_idx] 

            text_html = (f"<span style='color:{keyframe_color_code};'>{start_frame_idx + 1:02d}</span>" 
                         f"<span style='color:{default_text_color_code};'> ~ {end_frame_idx + 1:02d} : </span>" 
                         f"<span style='color:{keyframe_color_code};'>{motion_name}</span>") 

            motion_item = QListWidgetItem() 
            motion_label = QLabel(text_html) 
            motion_label.setStyleSheet("background-color: transparent; padding: 1px 0px;") 
            motion_label.setAttribute(Qt.WA_TransparentForMouseEvents, True) 

            self.motion_list.addItem(motion_item) 
            self.motion_list.setItemWidget(motion_item, motion_label) 
            motion_item.setData(Qt.UserRole, start_frame_idx) 
            
            # 모션 리스트 아이템 높이: 폰트 높이 + 늘린 패딩 (잘림 방지)
            motion_item_height = font_metrics_motion.height() + item_vertical_padding * 3 # 기존 *2 에서 *3으로 변경 (총 6px)
            motion_item.setSizeHint(QSize(motion_label.sizeHint().width(), motion_item_height))


            header_text = f"--- {motion_name} ({self._format_frame_number(start_frame_idx)} ~ {self._format_frame_number(end_frame_idx)}) ---"
            header_item_preview = QListWidgetItem(header_text)
            header_item_preview.setTextAlignment(Qt.AlignmentFlag.AlignCenter); header_item_preview.setForeground(QColor("#FFA07A"))
            header_item_preview.setData(Qt.UserRole, -1) 
            self.frame_preview.addItem(header_item_preview)
            
            preview_header_height = int((font_metrics_preview.height() + item_vertical_padding) * preview_item_height_reduction_factor)
            if preview_header_height < font_metrics_preview.height(): preview_header_height = font_metrics_preview.height()
            header_item_preview.setSizeHint(QSize(self.frame_preview.width() -20 , preview_header_height))

            for frame_idx_in_segment in range(start_frame_idx, end_frame_idx + 1):
                if 0 <= frame_idx_in_segment < len(self.all_frame_data): 
                    delay = self.all_frame_data[frame_idx_in_segment]['delay']
                    frame_desc = f"{self._format_frame_number(frame_idx_in_segment)} : {delay}ms"
                    frame_item_preview = QListWidgetItem(frame_desc)
                    frame_item_preview.setData(Qt.UserRole, frame_idx_in_segment) 
                    if self.selected_index == frame_idx_in_segment : frame_item_preview.setForeground(QColor("cyan")) 
                    self.frame_preview.addItem(frame_item_preview)
                    
                    preview_item_height = int((font_metrics_preview.height() + item_vertical_padding) * preview_item_height_reduction_factor)
                    if preview_item_height < font_metrics_preview.height(): preview_item_height = font_metrics_preview.height()
                    frame_item_preview.setSizeHint(QSize(frame_item_preview.sizeHint().width(), preview_item_height))

        self._sync_motion_list_selection() 

    def clear_timeline(self):
        while self.timeline_layout.count(): 
            item = self.timeline_layout.takeAt(0) 
            if item.widget(): item.widget().deleteLater() 
        self.frame_buttons.clear() 

    def closeEvent(self, event):
        if self.unsaved_changes: 
            reply = QMessageBox.question(self, "종료 확인", "저장되지 않은 변경사항이 있습니다. 종료 전에 저장하시겠습니까?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
            if reply == QMessageBox.StandardButton.Save: 
                self.save_settings() 
                if self.unsaved_changes: event.ignore(); return 
            elif reply == QMessageBox.StandardButton.Cancel: event.ignore(); return 
        event.accept() 

if __name__ == "__main__":
    app = QApplication(sys.argv) 
    window = GifSplitterUI() 
    window.show() 
    sys.exit(app.exec()) 
