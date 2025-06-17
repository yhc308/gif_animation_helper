# ===================================================
# 이름: Gif_Animation_Sampler (Test Version)
# 버전: v0.62.36_strippedBuild_GIF_v039
# 제작자: 윤희찬 (원본) / AI 협업 수정
# 설명: [v0.39 업데이트] - UI 표시 규칙 개선
#       - [수정] '잠긴 간략 종료 키프레임'의 이름이 '(잠김)'으로 올바르게 표시되도록 우선순위 수정.
#       - [개선] '간략 모션'의 키프레임 마커 색상도 다른 모션들과 동일하게
#         주황/분홍으로 번갈아 표시되도록 수정.
# ===================================================

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QListWidget, QLineEdit, QFileDialog, QScrollArea, QGridLayout, QMessageBox,
    QListWidgetItem, QInputDialog, QGraphicsView, 
    QGraphicsScene, QGraphicsPixmapItem, QStatusBar, QDialog, QButtonGroup,
    QStyleOptionButton, QStyle
)
from PySide6.QtGui import (
    QPixmap, QImage, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QKeySequence
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal, QRectF, QByteArray, QRect
import sys, os
import json
import traceback
from PIL import Image, ImageSequence
import bisect

# ===================================================
# 사용자 정의 위젯
# ===================================================
class TimelinePainterWidget(QWidget):
    """타임라인의 모든 배경 시각화 요소를 그리는 위젯."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.drawing_instructions = []

    def set_drawing_instructions(self, instructions):
        self.drawing_instructions = instructions
        self.update() 

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.drawing_instructions:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for instruction in self.drawing_instructions:
            style = instruction.get('style')
            
            if style == 'base_bg':
                painter.fillRect(instruction['rect'], instruction['color'])

            elif style == 'inner_highlight':
                rect = instruction['rect']
                color = QColor(instruction['color'])
                color.setAlphaF(0.4)
                
                pen = QPen(color, 3)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(2, 2, -1, -1))
            
            elif style == 'custom_dashed_border':
                rect = instruction['rect']
                color = instruction['color']
                pattern = instruction['pattern']
                
                pen = QPen(color, 2)
                pen.setDashPattern(pattern)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))

class FrameButton(QPushButton):
    """더블 클릭 시 자신의 인덱스를 포함하는 시그널을 보내는 버튼."""
    doubleClickedWithIndex = Signal(int)

    def __init__(self, text, index, parent=None):
        super().__init__(text, parent)
        self.index = index

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClickedWithIndex.emit(self.index)
        super().mouseDoubleClickEvent(event)

class CheckableButton(QPushButton):
    """체크 상태에 따라 좌측에 체크박스를, 중앙에 텍스트를 별도로 그리는 커스텀 버튼."""
    def __init__(self, text, checkmark_pixmap, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.checkmark_pixmap = checkmark_pixmap
        self.toggled.connect(self.update)

    def paintEvent(self, event):
        painter = QPainter(self)
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        
        original_text = opt.text
        opt.text = ""
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, painter, self)
        
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        check_box_size = 16
        check_box_margin = 10
        checkbox_rect = QRectF(check_box_margin, (self.height() - check_box_size) / 2, check_box_size, check_box_size)
        
        if self.isChecked():
            painter.setBrush(QColor("#ffa500"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(checkbox_rect, 3, 3)
            icon_rect = checkbox_rect.adjusted(2, 2, -2, -2)
            painter.drawPixmap(icon_rect.toRect(), self.checkmark_pixmap)
        else:
            pen = QPen(QColor("#ffa500"), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(checkbox_rect, 3, 3)

        painter.setPen(QColor("white"))
        text_rect = self.rect().adjusted(0, 0, -10, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, original_text)

class KeyframeSettingsDialog(QDialog):
    """키프레임의 상세 정보(이름, 타입, 루프 등)를 설정하기 위한 새로운 다이얼로그."""
    def __init__(self, frame_index, all_keyframes, keyframe_data=None, placeholder_text=None, parent=None):
        super().__init__(parent)

        self.frame_index = frame_index
        self.all_keyframes = all_keyframes
        self.keyframe_data = keyframe_data if keyframe_data else {}
        self.original_name = self.keyframe_data.get("name", "")
        self.placeholder_text = placeholder_text
        self.is_deleted = False

        self.setWindowTitle(f"프레임 {frame_index + 1} - 키프레임 설정")
        self.setStyleSheet("QDialog { background-color: #2A2A2A; color: white; }")
        self.setMinimumWidth(380)
        
        main_layout = QVBoxLayout(self)

        name_layout = QHBoxLayout()
        name_label = QLabel("모션 이름:")
        name_label.setStyleSheet("font-weight: bold; background: transparent;")
        self.name_input = QLineEdit()
        self.name_input.setStyleSheet("""
            QLineEdit {
                background-color: #202020;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px;
            }
            QLineEdit::placeholder {
                color: #808080;
            }
            QLineEdit:disabled {
                background-color: #252525;
                color: #777777;
            }
        """)
        if self.placeholder_text:
            self.name_input.setPlaceholderText(self.placeholder_text)
            
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        
        loop_layout = QHBoxLayout()
        loop_label = QLabel("루프 횟수:")
        loop_label.setStyleSheet("font-weight: bold; background: transparent;")
        self.loop_minus_btn = QPushButton("-")
        self.loop_value_label = QLabel("0")
        self.loop_value_label.setStyleSheet("background-color: #3C3C3C; border-radius: 3px; padding: 5px; font-weight: bold; min-width: 20px; qproperty-alignment: 'AlignCenter';")
        self.loop_plus_btn = QPushButton("+")
        self.loop_widgets = [loop_label, self.loop_minus_btn, self.loop_value_label, self.loop_plus_btn]
        for btn in [self.loop_minus_btn, self.loop_plus_btn]:
            btn.setFixedSize(24, 24)
            btn.setStyleSheet("background-color: #444; border-radius: 12px;")
        loop_layout.addWidget(loop_label)
        loop_layout.addStretch()
        loop_layout.addWidget(self.loop_minus_btn)
        loop_layout.addWidget(self.loop_value_label)
        loop_layout.addWidget(self.loop_plus_btn)

        type_layout = QHBoxLayout()
        self.start_key_btn = QPushButton("시작 키프레임")
        self.middle_key_btn = QPushButton("중간 키프레임")
        self.finish_key_btn = QPushButton("종료 키프레임")
        self.key_type_buttons_map = {
            1: self.start_key_btn, 2: self.middle_key_btn, 9: self.finish_key_btn
        }
        self.key_type_button_group = QButtonGroup(self)
        self.key_type_button_group.setExclusive(True)
        
        type_layout.addWidget(self.start_key_btn)
        type_layout.addWidget(self.middle_key_btn)
        type_layout.addWidget(self.finish_key_btn)
        
        for btn_id, btn in self.key_type_buttons_map.items():
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { 
                    background-color: #3C3C3C; 
                    border: 1px solid #555; 
                    padding: 8px; 
                    border-radius: 5px; 
                }
                QPushButton:checked { 
                    background-color: #5a91c3; 
                    border-color: #7ab3e6; 
                }
                QPushButton:disabled {
                    background-color: #2A2A2A;
                    color: #555555;
                }
            """)
            self.key_type_button_group.addButton(btn, btn_id)

        bottom_layout = QHBoxLayout()
        checkmark_svg_str = "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'><path fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' d='M5 13l4 4L19 7'/></svg>"
        q_byte_array = QByteArray(checkmark_svg_str.encode("utf-8"))
        checkmark_pixmap = QPixmap()
        checkmark_pixmap.loadFromData(q_byte_array)
        self.locked_checkbox = CheckableButton("잠긴 키로 설정", checkmark_pixmap)
        self.locked_checkbox.setStyleSheet("background-color: #3C3C3C; border: none; border-radius: 5px;")
        self.locked_checkbox.setFixedSize(140, 32)
        bottom_layout.addWidget(self.locked_checkbox)
        bottom_layout.addStretch()
        self.delete_btn = QPushButton("키프레임 삭제")
        
        self.delete_btn.setStyleSheet("""
            QPushButton { 
                background-color: #F44336; 
                color: white; 
                padding: 8px; 
                border-radius: 5px;
            }
            QPushButton:disabled { 
                background-color: #8B2222; 
                color: #AAAAAA; 
            }
        """)
        bottom_layout.addWidget(self.delete_btn)
        
        self.ok_btn = QPushButton("등록/수정")
        self.ok_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px; border-radius: 5px;")
        bottom_layout.addWidget(self.ok_btn)
        
        self.ok_btn.clicked.connect(self.accept)
        self.loop_plus_btn.clicked.connect(lambda: self._change_loop_count(1))
        self.loop_minus_btn.clicked.connect(lambda: self._change_loop_count(-1))
        self.key_type_button_group.idClicked.connect(self._on_key_type_changed)
        self.locked_checkbox.toggled.connect(self._on_locked_changed)

        main_layout.addLayout(name_layout)
        main_layout.addSpacing(10)
        main_layout.addLayout(loop_layout)
        main_layout.addSpacing(10)
        main_layout.addLayout(type_layout)
        main_layout.addSpacing(20)
        main_layout.addLayout(bottom_layout)
        
        self.adjustSize() 

        self._populate_data()
        self._update_ui_states()

    def _update_ui_states(self):
        is_locked = self.locked_checkbox.isChecked()
        key_type = self.key_type_button_group.checkedId()
        is_simple_end = self.parent()._is_simple_end_motion(self.frame_index)
        
        if is_locked:
            self.name_input.setText("(잠김)")
            self.name_input.setEnabled(False)
            self.middle_key_btn.setEnabled(False)
            for widget in self.loop_widgets:
                widget.setEnabled(False)
        else:
            self.middle_key_btn.setEnabled(True)
            for widget in self.loop_widgets:
                widget.setEnabled(True)
            
            is_finish_key = (key_type == 9)
            self.name_input.setEnabled(not is_finish_key)
            if is_finish_key:
                self.name_input.setText("")

            if is_simple_end:
                self.name_input.setText("(종료 키프레임)")
                self.name_input.setEnabled(False)

    def _on_key_type_changed(self, btn_id):
        if not self.locked_checkbox.isChecked():
            if btn_id == 1:
                self.name_input.setText(self.original_name)
            elif btn_id == 2:
                start_name = self._get_start_motion_name()
                if start_name:
                    self.name_input.setText(f"{start_name}-중간")
        self._update_ui_states()
        
    def _on_locked_changed(self, is_checked):
        if is_checked and self.middle_key_btn.isChecked():
            self.start_key_btn.setChecked(True)
        self._update_ui_states()

    def _is_simple_end_motion(self, frame_index):
        parent = self.parent()
        if not hasattr(parent, '_get_keyframe_context_for_frame'):
            return False
            
        context = parent._get_keyframe_context_for_frame(frame_index)
        return context["type"] == "simple_end" and context["end"] == frame_index

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.accept()
        else:
            super().keyPressEvent(event)

    def _change_loop_count(self, delta):
        if self.locked_checkbox.isChecked():
            return
        current_val = int(self.loop_value_label.text())
        new_val = max(0, min(9, current_val + delta))
        self.loop_value_label.setText(str(new_val))

    def _get_start_motion_name(self):
        sorted_keys = sorted([k for k in self.all_keyframes.keys() if k <= self.frame_index])
        for key in reversed(sorted_keys):
            if self.all_keyframes[key].get("type") == 1:
                return self.all_keyframes[key].get("name")
        return None

    def _populate_data(self):
        self.name_input.setText(self.keyframe_data.get("name", ""))
        self.loop_value_label.setText(str(self.keyframe_data.get("loop", 0)))
        
        key_type = self.keyframe_data.get("type", 1)
        button_to_check = self.key_type_button_group.button(key_type)
        if button_to_check:
            button_to_check.setChecked(True)
        else:
            self.key_type_button_group.button(1).setChecked(True)
            
        self.locked_checkbox.setChecked(self.keyframe_data.get("locked", False))

    def get_data(self):
        name = self.name_input.text()
        if not name and self.placeholder_text:
            name = self.placeholder_text
            
        return {
            "name": name,
            "type": self.key_type_button_group.checkedId(),
            "loop": int(self.loop_value_label.text()),
            "locked": self.locked_checkbox.isChecked()
        }

# ===================================================
# 메인 애플리케이션 클래스
# ===================================================
class GifSamplerTestVersion(QWidget):
    def __init__(self):
        super().__init__()
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        self.icon_base_path = os.path.join(base_path, "buttons")
        
        self.setWindowTitle("Gif_Animation_Sampler (v0.62.36_strippedBuild_GIF_v039)")
        self.setStyleSheet("background-color: #202020; color: white;")
        self.setMinimumSize(1280, 720)

        self.gif_path = None
        self.project_path = None
        self.keyframes = {}
        self.frame_buttons = []
        self.selected_index = None
        self.unsaved_changes = False
        self.all_frame_data = []
        self._is_programmatically_updating_lists = False
        
        self.playback_timer = QTimer(self)
        self.playback_timer.setSingleShot(True)
        self.current_playback_frame_index = -1
        
        self.is_in_complete_motion_loop = False 
        self.loop_return_point = -1
        self.loop_end_point = -1
        self.sub_loop_counters = {}
        
        self.status_bar = QStatusBar()
        self.status_label = QLabel("준비 완료. GIF 파일을 불러오세요.")
        
        self._init_ui()
        self._connect_signals()
        
    def _init_ui(self):
        main_app_layout = QVBoxLayout(self)
        main_app_layout.setContentsMargins(0, 0, 0, 0)
        main_app_layout.setSpacing(0)

        content_area_widget = QWidget()
        content_area_layout = QVBoxLayout(content_area_widget)
        content_area_layout.setContentsMargins(6, 6, 6, 6)
        content_area_layout.setSpacing(6)
        
        self.status_bar.setStyleSheet("background-color: #202020; border-top: 1px solid #353535;")
        self.status_bar.addWidget(self.status_label, 1)

        top_bar_layout = QGridLayout()
        self.new_project_btn = QPushButton("새 프로젝트 시작")
        self.load_btn = QPushButton("GIF 열기")
        self.save_btn = QPushButton("설정 저장")
        self.load_cfg_btn = QPushButton("설정 불러오기")
        file_buttons = [self.new_project_btn, self.load_btn, self.save_btn, self.load_cfg_btn]
        file_button_layout = QHBoxLayout()
        for btn in file_buttons:
            btn.setFixedHeight(32)
            btn.setStyleSheet("background-color: #303030; color: white; border-radius: 5px; padding: 0 10px;")
            file_button_layout.addWidget(btn)
        top_bar_layout.addLayout(file_button_layout, 0, 0, Qt.AlignLeft)

        self._init_playback_buttons()
        playback_controls_layout = QHBoxLayout()
        for btn in self.playback_buttons_group:
            playback_controls_layout.addWidget(btn)
        top_bar_layout.addLayout(playback_controls_layout, 0, 1, Qt.AlignCenter)

        top_right_layout = QHBoxLayout()
        self.filename_label = QLabel("현재 작업중 : 없음")
        self.filename_label.setStyleSheet("color: #AAAAAA;")
        self.settings_btn = QPushButton(QIcon(os.path.join(self.icon_base_path, "0setting.png")), "")
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setToolTip("설정 (기능 비활성화됨)")
        self.settings_btn.setEnabled(False) 
        top_right_layout.addWidget(self.filename_label, 1, Qt.AlignRight)
        top_right_layout.addWidget(self.settings_btn)
        top_bar_layout.addLayout(top_right_layout, 0, 2, Qt.AlignRight)
        top_bar_layout.setColumnStretch(0, 1)
        top_bar_layout.setColumnStretch(1, 0)
        top_bar_layout.setColumnStretch(2, 1)
        content_area_layout.addLayout(top_bar_layout)
        
        timeline_container = QWidget()
        self.timeline_layout = QHBoxLayout(timeline_container)
        self.timeline_layout.setSpacing(0)
        self.timeline_layout.setAlignment(Qt.AlignLeft)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        
        self.timeline_painter = TimelinePainterWidget(timeline_container)
        self.timeline_painter.setLayout(self.timeline_layout)
        
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setWidget(self.timeline_painter)
        self.timeline_scroll.setFixedHeight(40)
        content_area_layout.addWidget(self.timeline_scroll)

        left_panel = QVBoxLayout()
        self.selected_frame_label = QLabel("선택 중인 프레임: -")
        self.primary_keyframe_btn = QPushButton("키프레임 설정/모션등록")
        self.motion_list = QListWidget()
        left_panel.addWidget(self.selected_frame_label)
        left_panel.addWidget(self.primary_keyframe_btn)
        left_panel.addWidget(self.motion_list)

        center_panel = QVBoxLayout()
        self.frame_preview_label = QLabel("프레임 설명 미리보기")
        self.copy_desc_button = QPushButton("내용 복사")
        self.frame_preview = QListWidget()
        center_title_layout = QHBoxLayout()
        center_title_layout.addWidget(self.frame_preview_label)
        center_title_layout.addStretch()
        center_title_layout.addWidget(self.copy_desc_button)
        center_panel.addLayout(center_title_layout)
        center_panel.addWidget(self.frame_preview)
        
        right_panel = QVBoxLayout()
        self.graphics_scene = QGraphicsScene(self)
        self.pixmap_item = QGraphicsPixmapItem()
        self.graphics_scene.addItem(self.pixmap_item)
        self.graphics_view = QGraphicsView(self.graphics_scene)
        self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.graphics_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        right_panel.addWidget(self.graphics_view)

        middle_panel = QHBoxLayout()
        middle_panel.addLayout(left_panel, 2)
        middle_panel.addLayout(center_panel, 2)
        middle_panel.addLayout(right_panel, 6)
        content_area_layout.addLayout(middle_panel, 1)
        
        main_app_layout.addWidget(content_area_widget, 1)
        main_app_layout.addWidget(self.status_bar)
        self.setLayout(main_app_layout)
    
    def _init_playback_buttons(self):
        icon_size = QSize(20, 20)
        button_size = QSize(32, 32)
        button_style = "background-color: #3C3C3C; border: 1px solid #2A2A2A; border-radius: 5px;"
        
        self.prev_btn = QPushButton(QIcon(os.path.join(self.icon_base_path, "3previous.png")), "")
        self.play_pause_btn = QPushButton(QIcon(os.path.join(self.icon_base_path, "1play.png")), "")
        self.play_pause_btn.setCheckable(True)
        self.next_btn = QPushButton(QIcon(os.path.join(self.icon_base_path, "5next.png")), "")
        self.loop_btn = QPushButton(QIcon(os.path.join(self.icon_base_path, "4loop.png")), "")
        self.loop_btn.setCheckable(True)
        
        self.playback_buttons_group = [self.prev_btn, self.play_pause_btn, self.next_btn, self.loop_btn]
        for btn in self.playback_buttons_group:
            btn.setIconSize(icon_size)
            btn.setFixedSize(button_size)
            btn.setStyleSheet(button_style)

    def _connect_signals(self):
        self.new_project_btn.clicked.connect(lambda: self.start_new_project(show_message=True))
        self.load_btn.clicked.connect(self.load_gif_file)
        self.save_btn.clicked.connect(self.save_settings)
        self.load_cfg_btn.clicked.connect(self.load_settings)
        
        self.primary_keyframe_btn.clicked.connect(self._on_primary_keyframe_button_clicked)
        self.motion_list.itemDoubleClicked.connect(self.edit_motion_name)
        self.motion_list.currentItemChanged.connect(self.on_motion_item_changed)
        self.frame_preview.currentItemChanged.connect(self.on_frame_preview_item_changed)
        
        self.play_pause_btn.toggled.connect(self._on_play_pause_toggled)
        self.loop_btn.toggled.connect(self._on_loop_toggled)
        self.prev_btn.clicked.connect(self._on_prev_keyframe_clicked)
        self.next_btn.clicked.connect(self._on_next_keyframe_clicked)
        self.playback_timer.timeout.connect(self._advance_frame)

    def _generate_next_suffix(self, i):
        if i < 0: return ""
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        result = ""
        while i >= 0:
            result = chars[i % 26] + result
            i = i // 26 - 1
        return result

    def _generate_next_motion_name(self):
        existing_names = {v.get('name') for v in self.keyframes.values()}
        i = 0
        while True:
            suffix = self._generate_next_suffix(i)
            name = f"모션{suffix}"
            if name not in existing_names:
                return name
            i += 1
            
    def _is_simple_end_motion(self, frame_index):
        context = self._get_keyframe_context_for_frame(frame_index)
        key_data = self.keyframes.get(frame_index)
        
        if not key_data or key_data.get('type') != 9:
            return False
            
        return context["type"] == "simple_end" and context["end"] == frame_index

    def save_settings(self):
        if not self.gif_path:
            QMessageBox.warning(self, "저장 오류", "먼저 GIF 파일을 불러와주세요.")
            return False
        path_to_save = self.project_path
        if not path_to_save:
            default_path = os.path.splitext(self.gif_path)[0] + ".gifproj"
            path_to_save, _ = QFileDialog.getSaveFileName(self, "설정 저장", default_path, "GIF 프로젝트 파일 (*.gifproj)")
        if path_to_save:
            project_data = {"gif_path": os.path.basename(self.gif_path), "keyframes": {str(k): v for k, v in self.keyframes.items()}}
            try:
                with open(path_to_save, 'w', encoding='utf-8') as f: json.dump(project_data, f, indent=2, ensure_ascii=False)
                self.unsaved_changes = False
                self.project_path = path_to_save
                self._update_status(f"설정 저장 완료: {os.path.basename(path_to_save)}", is_complete_success=True)
                return True
            except Exception as e: QMessageBox.critical(self, "저장 오류", f"설정 저장 중 오류 발생: {e}")
        return False

    def load_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "프로젝트 파일 열기", "", "GIF 프로젝트 파일 (*.gifproj)")
        if not path: return
        
        if not self.all_frame_data:
            QMessageBox.warning(self, "로드 오류", "먼저 GIF 파일을 불러와야 설정 파일을 로드할 수 있습니다.")
            return
            
        if not self._check_unsaved_changes_and_prompt(): return

        try:
            with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
            loaded_keyframes = data.get("keyframes", {})
            self.keyframes.clear()
            for k, v in loaded_keyframes.items():
                if 'type' not in v:
                    v['type'] = 1
                if isinstance(v, str): self.keyframes[int(k)] = {"name": v, "type": 1, "loop": 0, "locked": False}
                else: self.keyframes[int(k)] = v
            self.project_path = path
            self.unsaved_changes = False
            
            self.full_refresh()
            QMessageBox.information(self, "로드 완료", "설정을 성공적으로 불러왔습니다.")

        except Exception as e:
            QMessageBox.critical(self, "로드 오류", f"설정 파일 로드 중 오류 발생: {e}")

    def _on_primary_keyframe_button_clicked(self):
        if self.selected_index is None: return
        self._open_keyframe_dialog(self.selected_index)

    def _open_keyframe_dialog(self, frame_index):
        current_data = self.keyframes.get(frame_index)
        is_existing = current_data is not None
        
        placeholder_text = None
        if not is_existing:
            placeholder_text = self._generate_next_motion_name()

        dialog = KeyframeSettingsDialog(frame_index, self.keyframes, current_data, placeholder_text, self)
        dialog.delete_btn.setEnabled(is_existing)
        
        def handle_delete():
            reply = QMessageBox.question(self, "삭제 확인", "이 키프레임을 삭제하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                dialog.is_deleted = True 
                dialog.accept()

        dialog.delete_btn.clicked.connect(handle_delete)

        if dialog.exec():
            if dialog.is_deleted:
                if is_existing and frame_index in self.keyframes:
                    del self.keyframes[frame_index]
            else:
                new_data = dialog.get_data()
                if not new_data.get("name") and new_data.get("type") != 9:
                    if is_existing and frame_index in self.keyframes:
                        del self.keyframes[frame_index]
                else:
                    self.keyframes[frame_index] = new_data
            
            self.unsaved_changes = True
            self.full_refresh()

    def full_refresh(self):
        if not self.all_frame_data: return
        self.refresh_motion_list()
        motion_groups = self._get_motion_groups_for_styling()
        drawing_instructions = self.update_frame_button_styles(motion_groups)
        self.timeline_painter.set_drawing_instructions(drawing_instructions)
        self._update_primary_keyframe_button_ui()
        self._sync_list_selections()

    def _get_motion_groups_for_styling(self):
        # [v0.39 수정] 모든 모션 타입을 색상 교환 대상으로 포함
        if not self.keyframes or not self.all_frame_data:
            return []

        motion_groups = []
        processed_starts = set()
        
        for i in range(len(self.all_frame_data)):
            if i in processed_starts:
                continue

            context = self._get_keyframe_context_for_frame(i)
            if context["type"] != "none":
                start_key = context["start"]
                if start_key not in processed_starts:
                    # 'is_complete' 여부와 상관없이 모든 모션을 그룹에 추가
                    motion_groups.append({
                        'sub_motions': [{'start': start_key}],
                        'is_complete': True 
                    })
                    for j in range(start_key, context["end"] + 1):
                        processed_starts.add(j)
        return motion_groups
        
    def refresh_motion_list(self):
        self._is_programmatically_updating_lists = True
        self.motion_list.clear()
        self.frame_preview.clear()

        if not self.all_frame_data:
            self._is_programmatically_updating_lists = False
            return

        sorted_keys = sorted(self.keyframes.keys())
        processed_starts = set()

        for key in sorted_keys:
            context = self._get_keyframe_context_for_frame(key)
            if context["type"] == "none" or context["start"] in processed_starts:
                continue
            
            start_key = context["start"]
            processed_starts.add(start_key)
            end_key = context["end"]

            # [v0.39 수정] 잠금 여부를 이름보다 먼저 확인
            key_data = context["data"]
            is_locked = key_data.get("locked", False)
            
            if context["type"] == "simple_end":
                name = "(잠김)" if is_locked else "(종료 키프레임)"
                list_name = f"{start_key+1:02d}F ~ {end_key+1:02d}F: {name}"
                motion_item = QListWidgetItem(list_name)
                motion_item.setData(Qt.UserRole, start_key)
                self.motion_list.addItem(motion_item)
                continue

            sub_motion_keys = [k for k in sorted_keys if start_key <= k <= end_key and self.keyframes.get(k, {}).get('type') != 9]
            for i, sub_key in enumerate(sub_motion_keys):
                sub_data = self.keyframes.get(sub_key, {})
                
                if sub_data.get("locked", False):
                    name = "(잠김)"
                else:
                    name = sub_data.get('name', '이름 없음')
                
                if not name: continue

                sub_motion_end = end_key
                if i + 1 < len(sub_motion_keys):
                    sub_motion_end = sub_motion_keys[i+1] - 1
                
                prefix = "  ㄴ " if sub_key != start_key else ""
                
                list_name = f"{prefix}{sub_key+1:02d}F ~ {sub_motion_end+1:02d}F: {name}"
                motion_item = QListWidgetItem(list_name)
                motion_item.setData(Qt.UserRole, sub_key)
                self.motion_list.addItem(motion_item)

        last_header = None
        for i in range(len(self.all_frame_data)):
            context = self._get_keyframe_context_for_frame(i)
            header_text = ""
            name_to_show = ""

            if context["type"] != "none":
                # [v0.39 수정] 잠김 여부를 최우선으로 판단
                is_locked = context["data"].get("locked", False)
                if is_locked:
                    name_to_show = "(잠김)"
                elif context["type"] == "simple_end":
                    name_to_show = "(종료 키프레임)"
                else:
                    # 하위 모션의 시작점을 찾아 정확한 이름 표시
                    sub_motion_start_key = context["start"]
                    for sub in context.get("sub_motions", []):
                        if sub["start"] <= i <= sub["end"]:
                            sub_motion_start_key = sub["start"]
                            break
                    name_to_show = self.keyframes.get(sub_motion_start_key, {}).get("name", "이름 없음")

                header_text = f"--- {name_to_show} ({context['start']+1:02d}F~{context['end']+1:02d}F) ---"
            else:
                header_text = "--- (키프레임 없는 구간) ---"

            if header_text != last_header:
                header_item = QListWidgetItem(header_text)
                header_item.setTextAlignment(Qt.AlignCenter)
                self.frame_preview.addItem(header_item)
                last_header = header_text
            
            delay = self.all_frame_data[i]['delay']
            frame_item = QListWidgetItem(f"{i+1:02d}F : {delay}ms")
            frame_item.setData(Qt.UserRole, i)
            self.frame_preview.addItem(frame_item)

        self._is_programmatically_updating_lists = False
            
    def _update_status(self, message, is_loading=False, is_complete_success=False):
        self.status_label.setText(message)
        QApplication.processEvents()

    def _check_unsaved_changes_and_prompt(self):
        if not self.unsaved_changes: return True
        reply = QMessageBox.question(self, "변경사항 저장", "저장되지 않은 변경사항이 있습니다. 저장하시겠습니까?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Save: return self.save_settings()
        return reply != QMessageBox.StandardButton.Cancel

    def start_new_project(self, show_message=False):
        if not self._check_unsaved_changes_and_prompt(): return
        self._reset_project_state()
        if show_message: QMessageBox.information(self, "새 프로젝트", "새 프로젝트가 시작되었습니다.")
        self._update_status("작업 대기중.")

    def _reset_project_state(self):
        self._stop_playback_and_reset_ui()
        self.gif_path, self.project_path = None, None
        self.selected_index = None
        self.keyframes.clear()
        self.unsaved_changes = False
        self.all_frame_data = []
        
        self.clear_timeline_ui()
        
        self.filename_label.setText("현재 작업중 : 없음")
        self.selected_frame_label.setText("선택 중인 프레임: -")
        self.full_refresh()

    def clear_timeline_ui(self):
        for button in self.frame_buttons:
            button.deleteLater()
        self.frame_buttons.clear()
        self.motion_list.clear()
        self.frame_preview.clear()
        
    def load_gif_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "GIF 파일 열기", "", "GIF 파일 (*.gif)")
        if path: self._load_gif_from_path(path)

    def _load_gif_from_path(self, path):
        if not self._check_unsaved_changes_and_prompt(): return
        
        self._reset_project_state()
        self._update_status(f"'{os.path.basename(path)}' 로딩 중...", is_loading=True)
        
        load_success, error_msg = self._load_data_sources(path)
        if not load_success:
            QMessageBox.critical(self, "로드 오류", f"데이터 로드 중 오류 발생: {error_msg}")
            self._reset_project_state()
            return
        
        self._build_ui_from_data()

        if self.all_frame_data:
            self.select_frame(0, force_refresh=True)
            self.graphics_scene.setSceneRect(self.graphics_scene.itemsBoundingRect())
            self.graphics_view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        
        self._update_status(f"'{os.path.basename(self.gif_path)}' 로드 완료.", is_complete_success=True)

    def _load_data_sources(self, gif_path):
        try:
            self.gif_path = gif_path
            with Image.open(gif_path) as img:
                for frame in ImageSequence.Iterator(img):
                    self.all_frame_data.append({'image': frame.copy(), 'delay': frame.info.get("duration", 100)})
            
            self.project_path = os.path.splitext(gif_path)[0] + ".gifproj"
            if os.path.exists(self.project_path):
                with open(self.project_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_keyframes = data.get("keyframes", {})
                    for k, v in loaded_keyframes.items():
                        self.keyframes[int(k)] = v
            return True, None
        except Exception as e:
            return False, str(e)

    def _build_ui_from_data(self):
        self.filename_label.setText(f"현재 작업중 : {os.path.basename(self.gif_path)}")
        
        self.clear_timeline_ui()

        for i in range(len(self.all_frame_data)):
            btn = FrameButton(str(i + 1), i)
            btn.setFixedSize(26, 26)
            btn.clicked.connect(lambda checked=False, idx=i: self.select_frame(idx))
            btn.doubleClickedWithIndex.connect(self.handle_frame_button_double_click)
            self.timeline_layout.addWidget(btn)
            self.frame_buttons.append(btn)
        
        self.timeline_painter.setMinimumWidth(self.timeline_layout.sizeHint().width())

    def handle_frame_button_double_click(self, index):
        self.select_frame(index)
        self._open_keyframe_dialog(index)

    def select_frame(self, index, from_playback=False, force_refresh=False):
        if not (0 <= index < len(self.all_frame_data)): return
        
        context = self._get_keyframe_context_for_frame(index)
        is_locked = context["type"] != "none" and context["data"].get("locked", False)
        
        if is_locked and not from_playback:
             return

        if self.selected_index == index and not from_playback and not force_refresh: return
        if self.playback_timer.isActive() and not from_playback: self._stop_playback_and_reset_ui()
        
        self.selected_index = index
        pil_frame = self.all_frame_data[index]['image'].convert("RGBA")
        qimg = QImage(pil_frame.tobytes(), pil_frame.width, pil_frame.height, QImage.Format.Format_RGBA8888)
        self.pixmap_item.setPixmap(QPixmap.fromImage(qimg))
        self.selected_frame_label.setText(f"선택 중인 프레임: {index + 1} ({self.all_frame_data[index]['delay']}ms)")
        
        self.full_refresh()
        
        if not self.playback_timer.isActive(): self.current_playback_frame_index = index

    def update_frame_button_styles(self, motion_groups):
        drawing_instructions = []
        colors = [QColor("#ffa500"), QColor("#ff0078")]
        motion_color_map = {}
        color_index = 0
        
        for group in motion_groups:
            # is_complete 플래그를 더 이상 사용하지 않고 모든 그룹을 색상 교환 대상으로 함
            if group['sub_motions']:
                start_key = group['sub_motions'][0]['start']
                motion_color_map[start_key] = colors[color_index]
                color_index = (color_index + 1) % len(colors)
        
        for i, btn in enumerate(self.frame_buttons):
            is_keyframe = i in self.keyframes
            is_selected = (i == self.selected_index)
            
            style = ""
            border = ""
            
            context = self._get_keyframe_context_for_frame(i)
            is_in_locked_segment = context["type"] != "none" and context["data"].get("locked", False)

            if is_in_locked_segment:
                bg_color = "#2A2A2A"
                color = "#555555"
                border = "1px solid rgba(0, 0, 0, 0.5)" 

                if is_keyframe:
                    key_type = self.keyframes[i].get("type")
                    locked_border_color = QColor("#808080")
                    if key_type == 2:
                        drawing_instructions.append({
                            'style': 'custom_dashed_border',
                            'rect': btn.geometry(),
                            'color': locked_border_color,
                            'pattern': [1, 3]
                        })
                        border = "border: none;"
                    else:
                        border = f"2px solid {locked_border_color.name()}"
                
                style = f"background-color: {bg_color}; color: {color}; border: {border};"
                btn.setStyleSheet(style)
                continue 
            
            if is_selected:
                bg_color = "#FFFFFF"
                color = "black"
                border = "2px solid #ffffff"
                if is_keyframe:
                    border = "2px solid orange"
                style = f"background-color: {bg_color}; color: {color}; border: {border};"
            
            elif is_keyframe:
                bg_color = "#202020"
                color = "white"
                key_type = self.keyframes[i].get("type")
                
                border_color_hex = "orange"
                if context["type"] != "none" and context["start"] in motion_color_map:
                    border_color_hex = motion_color_map[context["start"]].name()

                if key_type == 2:
                    drawing_instructions.append({
                        'style': 'custom_dashed_border',
                        'rect': btn.geometry(),
                        'color': QColor(border_color_hex),
                        'pattern': [1, 3]
                    })
                    border = "border: none;"
                else:
                    border = f"2px solid {border_color_hex}"
                    
                style = f"background-color: {bg_color}; color: {color}; border: {border};"
            
            else:
                color = "white"
                border = "1px solid rgba(0, 0, 0, 0.5)"
                bg_color = "#353535"
                style = f"background-color: {bg_color}; color: {color}; border: {border};"
            
            btn.setStyleSheet(style)
        
        return drawing_instructions

    def _update_primary_keyframe_button_ui(self):
        if self.selected_index is not None and self.selected_index in self.keyframes:
            self.primary_keyframe_btn.setText("키프레임 수정/삭제")
            self.primary_keyframe_btn.setStyleSheet("background-color: #5a91c3; color: white;")
        else:
            self.primary_keyframe_btn.setText("새 키프레임 등록")
            self.primary_keyframe_btn.setStyleSheet("background-color: #4CAF50; color: white;")

    def _sync_list_selections(self):
        self._is_programmatically_updating_lists = True
        context = self._get_keyframe_context_for_frame(self.selected_index)
        
        motion_item_to_select = None
        if context["type"] != "none":
            key_to_find = context["start"]
            for sub in context.get("sub_motions", []):
                if sub["start"] <= self.selected_index <= sub["end"]:
                    key_to_find = sub["start"]
                    break
            
            for i in range(self.motion_list.count()):
                item = self.motion_list.item(i)
                if item.data(Qt.UserRole) == key_to_find:
                    motion_item_to_select = item
                    break 
        
        self.motion_list.setCurrentItem(motion_item_to_select)

        frame_item_to_select = None
        for i in range(self.frame_preview.count()):
            item = self.frame_preview.item(i)
            is_selected = item.data(Qt.UserRole) == self.selected_index
            item.setForeground(QColor("cyan") if is_selected else Qt.white)
            if is_selected:
                frame_item_to_select = item

        if frame_item_to_select:
            self.frame_preview.setCurrentItem(frame_item_to_select)
            self.frame_preview.scrollToItem(frame_item_to_select)

        self._is_programmatically_updating_lists = False
        
    def on_motion_item_changed(self, current, previous):
        if self._is_programmatically_updating_lists or not current: return
        start_idx = current.data(Qt.UserRole)
        if start_idx is not None:
            self.select_frame(start_idx)
                
    def on_frame_preview_item_changed(self, current, previous):
        if self._is_programmatically_updating_lists or not current: return
        idx = current.data(Qt.UserRole)
        if idx is not None and idx != -1:
            self.select_frame(idx)

    # --- Playback Logic ---
    def _on_play_pause_toggled(self, checked):
        if not self.all_frame_data: self.play_pause_btn.setChecked(False); return
        if checked:
            start_frame_index = self.selected_index if self.selected_index is not None else 0
            
            context = self._get_keyframe_context_for_frame(start_frame_index)
            if context["type"] != "none" and context["data"].get("locked", False):
                start_frame_index = self._find_next_unlocked_frame(start_frame_index)
                if start_frame_index == -1: 
                    self._stop_playback_and_reset_ui()
                    return

            self.current_playback_frame_index = start_frame_index
            self._update_playback_context(self.current_playback_frame_index)
            self._resume_playback(self.current_playback_frame_index)
        else: 
            self._stop_playback_and_reset_ui()

    def _reset_loop_state(self):
        self.is_in_complete_motion_loop = False
        self.loop_return_point = -1
        self.loop_end_point = -1
        self.sub_loop_counters.clear()

    def _update_playback_context(self, frame_index):
        self._reset_loop_state()
        context = self._get_keyframe_context_for_frame(frame_index)

        is_loopable_motion = context["type"] in ["complete", "simple", "simple_end"]
        
        if self.loop_btn.isChecked() and is_loopable_motion:
            self.is_in_complete_motion_loop = True
            self.loop_return_point = context["start"]
            self.loop_end_point = context["end"]
        
        self.sub_loop_counters.clear() 

    def _resume_playback(self, frame_index):
        if not (0 <= frame_index < len(self.all_frame_data)):
            self._stop_playback_and_reset_ui()
            return

        self.current_playback_frame_index = frame_index
        if not self.play_pause_btn.isChecked(): self.play_pause_btn.setChecked(True)
        self.play_pause_btn.setIcon(QIcon(os.path.join(self.icon_base_path, "2stop.png")))

        self.select_frame(self.current_playback_frame_index, from_playback=True)
        delay = self.all_frame_data[self.current_playback_frame_index]['delay']
        self.playback_timer.start(delay if delay > 0 else 100)
        
    def _on_loop_toggled(self, checked):
        if checked: self.loop_btn.setIcon(QIcon(os.path.join(self.icon_base_path, "4loop_pressed.png")))
        else:
            self.loop_btn.setIcon(QIcon(os.path.join(self.icon_base_path, "4loop.png")))
        if self.playback_timer.isActive():
            self._update_playback_context(self.current_playback_frame_index)

    def _stop_playback_and_reset_ui(self):
        self.playback_timer.stop()
        if self.play_pause_btn.isChecked(): self.play_pause_btn.setChecked(False)
        self.play_pause_btn.setIcon(QIcon(os.path.join(self.icon_base_path, "1play.png")))
        self._reset_loop_state()

    def _advance_frame(self):
        if not self.play_pause_btn.isChecked() or not self.all_frame_data:
            self._stop_playback_and_reset_ui()
            return

        current_frame = self.current_playback_frame_index
        context = self._get_keyframe_context_for_frame(current_frame)
        next_frame_index = -1

        if context["type"] == "none":
            next_frame_index = current_frame + 1
        else:
            has_looped_in_sub = False
            if context.get("sub_motions"):
                for sub_motion in context["sub_motions"]:
                    if current_frame == sub_motion["end"]:
                        key_data = sub_motion["data"]
                        target_loop = key_data.get('loop', 0)
                        current_loop_count = self.sub_loop_counters.get(sub_motion["start"], 0)
                        
                        if current_loop_count < target_loop:
                            next_frame_index = sub_motion["start"]
                            self.sub_loop_counters[sub_motion["start"]] = current_loop_count + 1
                            has_looped_in_sub = True
                        break
            
            if not has_looped_in_sub:
                if self.is_in_complete_motion_loop and current_frame == self.loop_end_point:
                    next_frame_index = self.loop_return_point
                    self.sub_loop_counters.clear()
                else:
                    next_frame_index = current_frame + 1

        if next_frame_index >= len(self.all_frame_data):
            if self.is_in_complete_motion_loop:
                next_frame_index = self.loop_return_point
                self.sub_loop_counters.clear()
            else:
                next_frame_index = 0
                self._update_playback_context(next_frame_index)

        final_next_frame = self._find_next_unlocked_frame(next_frame_index)
        
        if final_next_frame == -1:
             self._stop_playback_and_reset_ui()
             return
        
        new_context = self._get_keyframe_context_for_frame(final_next_frame)
        if context.get("start") != new_context.get("start"):
            self._update_playback_context(final_next_frame)

        self._resume_playback(final_next_frame)

    def _find_next_unlocked_frame(self, start_index):
        if not self.all_frame_data: return -1

        checked_count = 0
        idx = start_index
        while checked_count < len(self.all_frame_data):
            if idx >= len(self.all_frame_data):
                idx = 0
            
            context = self._get_keyframe_context_for_frame(idx)
            if context["type"] == "none" or not context["data"].get("locked", False):
                return idx

            idx += 1
            checked_count += 1
        
        return -1

    def _get_keyframe_context_for_frame(self, frame_index):
        default_context = {"start": None, "end": None, "data": {}, "type": "none", "sub_motions": []}
        if not self.keyframes or frame_index is None or not self.all_frame_data:
            return default_context
        
        sorted_keys = sorted(self.keyframes.keys())
        
        if sorted_keys:
            first_key = sorted_keys[0]
            first_key_data = self.keyframes[first_key]
            if first_key_data.get("type") == 9:
                is_simple_end = not any(k < first_key and self.keyframes[k].get("type") in [1, 2] for k in sorted_keys)
                
                is_locked_start_before = any(
                    k < first_key and self.keyframes[k].get("locked") and self.keyframes[k].get("type") != 9 
                    for k in sorted_keys
                )
                if is_simple_end and not is_locked_start_before:
                    if frame_index <= first_key:
                        return {"start": 0, "end": first_key, "data": first_key_data, "type": "simple_end", "sub_motions": [{"start":0, "end":first_key, "data":first_key_data}]}

        true_start_keys = sorted([k for k, v in self.keyframes.items() if (v.get("type") == 1 or (v.get("locked") and v.get("type") != 9)) or (v.get("type")==2 and not self._is_sub_motion(k, sorted_keys))])
        
        if not true_start_keys:
            return default_context

        insert_point = bisect.bisect_right(true_start_keys, frame_index)
        if insert_point == 0:
            return default_context

        start_key = true_start_keys[insert_point - 1]
        
        end_key = len(self.all_frame_data) - 1
        motion_type = "simple" 

        for key in sorted_keys:
            if key > start_key:
                key_data = self.keyframes[key]
                is_next_start = (key_data.get("type") == 1 or (key_data.get("locked") and key_data.get("type") != 9)) or (key_data.get("type")==2 and not self._is_sub_motion(key, sorted_keys))
                
                if is_next_start:
                    end_key = key - 1
                    break
                if key_data.get("type") == 9:
                    end_key = key
                    motion_type = "complete"
                    break
        
        if start_key <= frame_index <= end_key:
            sub_motions = []
            sub_motion_keys = [k for k in sorted_keys if start_key <= k <= end_key and self.keyframes[k].get('type') != 9]
            for i, sub_k in enumerate(sub_motion_keys):
                sub_end = end_key
                if i + 1 < len(sub_motion_keys):
                    sub_end = sub_motion_keys[i+1] - 1
                sub_motions.append({"start": sub_k, "end": sub_end, "data": self.keyframes[sub_k]})

            return {"start": start_key, "end": end_key, "data": self.keyframes[start_key], "type": motion_type, "sub_motions": sub_motions}

        return default_context

    def _is_sub_motion(self, key_index, sorted_keys):
        key_data = self.keyframes.get(key_index)
        if not key_data or key_data.get("type") != 2:
            return False

        current_key_idx_in_list = bisect.bisect_left(sorted_keys, key_index)
        if current_key_idx_in_list == 0:
            return False
        
        prev_key_index = sorted_keys[current_key_idx_in_list - 1]
        prev_key_data = self.keyframes[prev_key_index]

        if prev_key_data.get("type") in [1, 2]:
            for k in sorted_keys:
                if prev_key_index < k < key_index:
                    if self.keyframes[k].get("type") == 9:
                        return False
            return True
        
        return False

    def _on_prev_keyframe_clicked(self): self._navigate_keyframe(-1)
    def _on_next_keyframe_clicked(self): self._navigate_keyframe(1)

    def _navigate_keyframe(self, direction):
        if not self.keyframes: return
        was_playing = self.playback_timer.isActive()
        if was_playing: self._stop_playback_and_reset_ui()
        
        sorted_keys = sorted([k for k, v in self.keyframes.items() if not self._get_keyframe_context_for_frame(k)["data"].get("locked", False)])
        if not sorted_keys: return
        
        current_idx = self.selected_index
        if current_idx is None: current_idx = 0

        if direction == 1:
            insert_point = bisect.bisect_right(sorted_keys, current_idx)
            target_key = sorted_keys[insert_point] if insert_point < len(sorted_keys) else sorted_keys[0]
        else: 
            insert_point = bisect.bisect_left(sorted_keys, current_idx)
            target_key = sorted_keys[insert_point - 1] if insert_point > 0 else sorted_keys[-1]
        
        self.select_frame(target_key, from_playback=was_playing)
        if was_playing:
            self._update_playback_context(target_key)
            self._resume_playback(target_key)
        else:
            self.current_playback_frame_index = target_key

    def closeEvent(self, event):
        if self._check_unsaved_changes_and_prompt(): event.accept()
        else: event.ignore()
    
    def edit_motion_name(self, item):
        start_idx = item.data(Qt.UserRole)
        if start_idx is None: return
        key_data = self.keyframes.get(start_idx, {})
        if key_data.get("locked", False):
            return
        if self._is_simple_end_motion(start_idx):
            return
        self._open_keyframe_dialog(start_idx)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GifSamplerTestVersion()
    window.show()
    sys.exit(app.exec())
