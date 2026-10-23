"""In-process image/video viewer and cached media thumbnails using Qt Multimedia."""
from collections import deque
import hashlib
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QObject, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QStackedWidget, QDialog, QSizePolicy)

VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv', '.avi'}


def clock(ms):
    seconds = max(0, int(ms) // 1000)
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


class VideoCanvas(QLabel):
    """Raster video canvas also works over RDP and in offscreen render tests."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter); self.setObjectName('mediaCanvas')
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.frame_image = QPixmap()
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.paint_frame)

    def videoSink(self):
        return self.sink

    def setAspectRatioMode(self, _):
        pass  # all frames use KeepAspectRatio

    def paint_frame(self, frame):
        if frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.frame_image = QPixmap.fromImage(image); self.draw_frame()

    def draw_frame(self):
        if not self.frame_image.isNull():
            self.setPixmap(self.frame_image.scaled(self.size()-QSize(12,12), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def reset(self):
        self.frame_image = QPixmap(); self.clear(); self.setText('Đang tải video…')

    def resizeEvent(self, event):
        super().resizeEvent(event); self.draw_frame()


class MediaViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path, self.original, self.poster_pending = None, QPixmap(), False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel('Chọn ảnh hoặc video để xem trực tiếp')
        self.title.setWordWrap(True)
        self.title.setObjectName('viewerTitle')
        title_row = QHBoxLayout()
        title_row.addWidget(self.title, 1)
        fullscreen = QPushButton('Phóng to')
        fullscreen.clicked.connect(self.enlarge)
        title_row.addWidget(fullscreen)
        layout.addLayout(title_row)
        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(240)
        self.image = QLabel('Ảnh / video sẽ hiển thị ở đây')
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setObjectName('mediaCanvas')
        self.video = VideoCanvas()
        self.video.setAspectRatioMode(Qt.KeepAspectRatio)
        self.stack.addWidget(self.image); self.stack.addWidget(self.video)
        layout.addWidget(self.stack, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoSink(self.video.videoSink())
        self.video.videoSink().videoFrameChanged.connect(self._frame)
        self.controls = QWidget()
        controls = QVBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.play = QPushButton('Phát')
        self.play.clicked.connect(self.toggle)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderReleased.connect(lambda: self.player.setPosition(self.seek.value()))
        self.seek.sliderMoved.connect(lambda value: self.time.setText(clock(value) + ' / ' + clock(self.player.duration())))
        self.time = QLabel('00:00 / 00:00')
        row.addWidget(self.play); row.addWidget(self.seek, 1); row.addWidget(self.time)
        controls.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('Âm lượng'))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100); self.volume.setValue(70)
        self.volume.setMaximumWidth(130)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        row.addWidget(self.volume)
        row.addStretch()
        controls.addLayout(row)
        layout.addWidget(self.controls)
        self.error = QLabel('')
        self.error.setWordWrap(True); self.error.setObjectName('warning')
        layout.addWidget(self.error)
        self.controls.hide()
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda duration: self.seek.setRange(0, max(0, int(duration))))
        self.player.playbackStateChanged.connect(lambda state: self.play.setText('Tạm dừng' if state == QMediaPlayer.PlayingState else 'Phát'))
        self.player.errorOccurred.connect(lambda *_: self.error.setText('Không phát được video: ' + self.player.errorString()))

    def load(self, path, autoplay=False):
        path = Path(path).resolve()
        if not path.is_file():
            self.error.setText('Không tìm thấy tệp kết quả'); return False
        self.player.stop(); self.player.setSource(QUrl())
        self.path = path
        self.error.setText(''); self.title.setText(path.name)
        self.seek.setValue(0); self.time.setText('00:00 / 00:00')
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            self.stack.setCurrentWidget(self.video); self.controls.show()
            self.video.reset()
            self.poster_pending = not autoplay
            self.audio.setMuted(not autoplay)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            # Decode a first frame even when the user has not pressed play yet.
            self.player.play()
        else:
            self.poster_pending = False; self.controls.hide()
            self.stack.setCurrentWidget(self.image)
            self.original = QPixmap(str(path))
            if self.original.isNull():
                self.image.setText('Không đọc được ảnh này'); return False
            self._resize_image()
        return True

    def _frame(self, frame):
        if self.poster_pending and frame.isValid():
            self.poster_pending = False
            QTimer.singleShot(0, self.player.pause)

    def _position(self, value):
        if not self.seek.isSliderDown():
            self.seek.setValue(int(value))
            self.time.setText(clock(value) + ' / ' + clock(self.player.duration()))

    def toggle(self):
        self.poster_pending = False
        self.audio.setMuted(False)
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def pause(self):
        self.poster_pending = False; self.player.pause()

    def shutdown(self):
        self.poster_pending = False; self.player.stop(); self.player.setSource(QUrl())

    def _resize_image(self):
        if not self.original.isNull():
            size = self.image.size() - QSize(12, 12)
            if size.width() > 0 and size.height() > 0:
                self.image.setPixmap(self.original.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event); self._resize_image()

    def enlarge(self):
        if not self.path:
            return
        path = self.path
        position = self.player.position()
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.pause()
        dialog = QDialog(self)
        dialog.setWindowTitle(self.path.name); dialog.resize(1000, 700)
        layout = QVBoxLayout(dialog)
        viewer = MediaViewer(dialog); layout.addWidget(viewer)
        viewer.volume.setValue(self.volume.value())
        restored = [False]
        def resume_position(frame):
            if not restored[0] and frame.isValid():
                restored[0] = True
                def seek_after_poster():
                    viewer.poster_pending=False; viewer.player.pause(); viewer.player.setPosition(position)
                    if playing:
                        viewer.audio.setMuted(False); viewer.player.play()
                # FFmpeg may reset an early seek during initial loading. Seek
                # once the first decoded frame has established the timeline.
                QTimer.singleShot(50,seek_after_poster)
        viewer.video.videoSink().videoFrameChanged.connect(resume_position)
        viewer.load(path, autoplay=False)
        def finish(_):
            end_position = viewer.player.position()
            continue_playing = viewer.player.playbackState() == QMediaPlayer.PlayingState
            volume = viewer.volume.value()
            viewer.shutdown()
            if self.path == path and not self.player.source().isEmpty():
                self.volume.setValue(volume); self.player.setPosition(end_position)
                if continue_playing:
                    self.audio.setMuted(False); self.player.play()
        dialog.finished.connect(finish)
        dialog.exec()


class ThumbnailQueue(QObject):
    ready = Signal(str, QImage)

    def __init__(self, cache_dir, parent=None):
        super().__init__(parent)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.jobs, self.waiting, self.active = deque(), set(), None
        self.player = QMediaPlayer(self)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.frame)
        self.player.errorOccurred.connect(lambda *_: self.finish(None))
        self.timeout = QTimer(self); self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda: self.finish(None))

    def request(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            return
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            image = QImage(str(path))
            if not image.isNull():
                self.ready.emit(str(path), image.scaled(240, 144, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            return
        stat = path.stat()
        key = hashlib.sha256(f'{path}|{stat.st_mtime_ns}|{stat.st_size}'.encode()).hexdigest()
        cached = self.cache_dir / (key + '.jpg')
        if cached.is_file():
            image = QImage(str(cached))
            if not image.isNull():
                self.ready.emit(str(path), image); return
        if str(path) not in self.waiting:
            self.waiting.add(str(path)); self.jobs.append((path, cached))
            if self.active is None:
                QTimer.singleShot(0, self.next)

    def next(self):
        if self.active is not None or not self.jobs:
            return
        self.active = self.jobs.popleft()
        self.player.setSource(QUrl.fromLocalFile(str(self.active[0])))
        self.timeout.start(8000); self.player.play()

    def frame(self, frame):
        if self.active is not None and frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.finish(image)

    def finish(self, image):
        if self.active is None:
            return
        path, cached = self.active; self.active = None
        self.timeout.stop(); self.player.stop(); self.player.setSource(QUrl())
        self.waiting.discard(str(path))
        if image is not None:
            image = image.scaled(240, 144, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image.save(str(cached), 'JPG', 85)
            self.ready.emit(str(path), image)
        QTimer.singleShot(0, self.next)

    def shutdown(self):
        self.timeout.stop(); self.jobs.clear(); self.waiting.clear(); self.active = None
        self.player.stop(); self.player.setSource(QUrl())
