#!/usr/bin/env python3
"""
Affinity Linux Installer - PyQt6 GUI Version
A modern, professional GUI application for installing Affinity software on Linux
"""

import os
import sys
import subprocess
import shutil
import tarfile
import zipfile
import threading
import platform
import urllib.request
import urllib.error
import re
import json
import tempfile
from pathlib import Path
import time
import signal
import shlex


def detect_distro_for_install():
    """Detect distribution for package installation"""
    try:
        with open("/etc/os-release", "r") as f:
            content = f.read()
        for line in content.split("\n"):
            if line.startswith("ID="):
                distro = line.split("=", 1)[1].strip().strip('"').lower()
                if distro == "pika":
                    distro = "pikaos"
                return distro
    except (IOError, FileNotFoundError):
        pass
    return None


def install_package(package_name, import_name=None):
    """Install a Python package if not available"""
    if import_name is None:
        import_name = package_name

    try:
        __import__(import_name)
        return True
    except ImportError:
        print(f"Installing {package_name}...")

        distro = detect_distro_for_install()
        pip_flags = ["--user"]
        if distro in ["arch", "artix", "cachyos", "manjaro", "endeavouros", "xerolinux"]:
            pip_flags.append("--break-system-packages")
        if not sys.stdout.isatty():
            pip_flags.insert(0, "--quiet")

        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package_name] + pip_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                __import__(import_name)
                print(f"✓ {package_name} installed successfully")
                return True
            except ImportError:
                print(f"✗ Failed to import {package_name} after installation")
                return False
        except subprocess.CalledProcessError:
            print(f"✗ Failed to install {package_name} via pip")
            return False
        except Exception as e:
            print(f"✗ Error installing {package_name}: {e}")
            return False


PYQT6_AVAILABLE = False
try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLabel,
        QFileDialog,
        QMessageBox,
        QTextEdit,
        QFrame,
        QProgressBar,
        QGroupBox,
        QScrollArea,
        QDialog,
        QDialogButtonBox,
        QButtonGroup,
        QRadioButton,
        QInputDialog,
        QSlider,
        QLineEdit,
        QSizePolicy,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
    from PyQt6.QtGui import (
        QFont,
        QColor,
        QPalette,
        QIcon,
        QPixmap,
        QShortcut,
        QKeySequence,
        QWheelEvent,
        QPainter,
        QPen,
    )

    # Try to import SVG widget (may not be available on all distributions)
    try:
        from PyQt6.QtSvgWidgets import QSvgWidget

        SVG_WIDGET_AVAILABLE = True
    except ImportError:
        print("⚠️  QSvgWidget not available - some icons may not display correctly")
        SVG_WIDGET_AVAILABLE = False

        # Create a dummy QSvgWidget class to prevent import errors
        class QSvgWidget(QWidget):
            def load(self, content):
                pass

            def setFixedSize(self, size):
                super().setFixedSize(size)

    PYQT6_AVAILABLE = True
except ImportError:
    print("PyQt6 not found. Attempting to install...")
    if install_package("PyQt6", "PyQt6"):
        try:
            from PyQt6.QtWidgets import (
                QApplication,
                QMainWindow,
                QWidget,
                QVBoxLayout,
                QHBoxLayout,
                QPushButton,
                QLabel,
                QFileDialog,
                QMessageBox,
                QTextEdit,
                QFrame,
                QProgressBar,
                QGroupBox,
                QScrollArea,
                QDialog,
                QDialogButtonBox,
                QButtonGroup,
                QRadioButton,
                QInputDialog,
                QSlider,
                QLineEdit,
                QSizePolicy,
            )
            from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
            from PyQt6.QtGui import (
                QFont,
                QColor,
                QPalette,
                QIcon,
                QPixmap,
                QShortcut,
                QKeySequence,
                QWheelEvent,
                QPainter,
                QPen,
            )

            # Try to import SVG widget after installation
            try:
                from PyQt6.QtSvgWidgets import QSvgWidget

                SVG_WIDGET_AVAILABLE = True
            except ImportError:
                print(
                    "⚠️  QSvgWidget not available after installation - some icons may not display correctly"
                )
                SVG_WIDGET_AVAILABLE = False

                # Create a dummy QSvgWidget class to prevent import errors
                class QSvgWidget(QWidget):
                    def load(self, content):
                        pass

                    def setFixedSize(self, size):
                        super().setFixedSize(size)

            PYQT6_AVAILABLE = True
            print("✓ PyQt6 installed and imported successfully")
        except ImportError as e:
            print(f"✗ Failed to import PyQt6 after installation: {e}")
            PYQT6_AVAILABLE = False
    else:
        print("✗ Failed to install PyQt6 via pip")
        PYQT6_AVAILABLE = False

if not PYQT6_AVAILABLE:
    print("\nERROR: PyQt6 is required but could not be installed.")
    print("Please install PyQt6 manually using one of these methods:\n")
    print("Using pip:")
    print("  pip install --user PyQt6")
    print("\nOr using your distribution's package manager:")
    print("  Arch/Artix/CachyOS/EndeavourOS/XeroLinux: sudo pacman -S python-pyqt6")
    print("  Fedora/Nobara: sudo dnf install python3-pyqt6")
    print("  Debian/Ubuntu/Mint/Pop/Zorin/PikaOS: sudo apt install python3-pyqt6")
    print("  openSUSE: sudo zypper install python313-PyQt6")
    sys.exit(1)


class ZoomableTextEdit(QTextEdit):
    """QTextEdit with Ctrl+Wheel zoom support"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_in_callback = None
        self.zoom_out_callback = None

    def set_zoom_callbacks(self, zoom_in, zoom_out):
        """Set callbacks for zoom in/out"""
        self.zoom_in_callback = zoom_in
        self.zoom_out_callback = zoom_out

    def wheelEvent(self, event):
        """Handle mouse wheel events for zoom (Ctrl+Wheel) or scroll"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoomIn(1)
                if self.zoom_in_callback:
                    self.zoom_in_callback()
            elif delta < 0:
                self.zoomOut(1)
                if self.zoom_out_callback:
                    self.zoom_out_callback()
        else:
            super().wheelEvent(event)


class ProgressSpinner(QWidget):
    """A simple rotating spinner widget (indeterminate progress)."""

    def __init__(self, size=22, line_width=3, color=QColor("#8ff361"), parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._on_timeout)
        self._size = size
        self._line_width = line_width
        self._color = color
        self.setFixedSize(self._size, self._size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def start(self):
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()
        self.update()

    def _on_timeout(self):
        self._angle = (self._angle - 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(
            self._line_width, self._line_width, -self._line_width, -self._line_width
        )
        pen = QPen(self._color)
        pen.setWidth(self._line_width)
        painter.setPen(pen)
        start_angle = int(self._angle * 16)
        span_angle = int(270 * 16)
        painter.drawArc(rect, start_angle, span_angle)
        painter.end()


class AffinityInstallerGUI(QMainWindow):
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(float)
    progress_text_signal = pyqtSignal(str)
    show_message_signal = pyqtSignal(str, str, str)
    sudo_password_dialog_signal = pyqtSignal()
    interactive_prompt_signal = pyqtSignal(str, str)
    question_dialog_signal = pyqtSignal(str, str, list)
    nvidia_dxvk_vkd3d_choice_signal = pyqtSignal()
    prompt_affinity_install_signal = pyqtSignal()
    install_application_signal = pyqtSignal(str)
    show_spinner_signal = pyqtSignal(object)
    hide_spinner_signal = pyqtSignal(object)
    gpu_selection_signal = pyqtSignal()

    def __init__(self):
        startup_start = time.time()
        timing_log = []

        def log_timing(step_name, start_time):
            elapsed = time.time() - start_time
            timing_log.append((step_name, elapsed))
            return time.time()

        step_start = time.time()
        super().__init__()
        step_start = log_timing("QMainWindow.__init__", step_start)

        self.setWindowTitle("Affinity Linux Installer")
        screen = self.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        min_width = max(640, int(screen_width * 0.7))
        min_height = max(480, int(screen_height * 0.7))
        self.setMinimumSize(min_width, min_height)

        default_width = min(1200, int(screen_width * 0.8))
        default_height = min(900, int(screen_height * 0.8))
        self.resize(default_width, default_height)
        step_start = log_timing("Window setup", step_start)

        self.distro = None
        self.distro_version = None
        self.directory = str(Path.home() / ".AffinityLinux")
        self.setup_complete = False
        self.installer_file = None
        self.update_buttons = {}
        self.switch_backend_button = None
        self.log_font_size = 11
        self.operation_cancelled = False
        self.current_operation = None
        self.operation_in_progress = False
        self.sudo_password = None
        self.sudo_password_validated = False
        self.interactive_response = None
        self.waiting_for_response = False
        self.question_dialog_response = None
        self.waiting_for_question_response = False
        self.nvidia_dxvk_vkd3d_choice_response = None
        self.waiting_for_nvidia_choice = False
        self.dark_mode = True
        self.icon_buttons = []
        self.enable_opencl = False
        self.cancel_event = threading.Event()
        self._process_lock = threading.Lock()
        self._active_processes = set()
        self._button_spinner_map = {}
        self._last_clicked_button = None
        self._operation_button = None

        self.log_file_path = Path.home() / "AffinitySetup.log"
        self.log_file = None
        self._init_log_file()
        step_start = log_timing("Log file init", step_start)

        self.log_signal.connect(self._log_safe)
        self.progress_signal.connect(self._update_progress_safe)
        self.progress_text_signal.connect(self._update_progress_text_safe)
        self.show_message_signal.connect(self._show_message_safe)
        self.sudo_password_dialog_signal.connect(self._request_sudo_password_safe)
        self.interactive_prompt_signal.connect(self._request_interactive_response_safe)
        self.question_dialog_signal.connect(self._show_question_dialog_safe)
        self.nvidia_dxvk_vkd3d_choice_signal.connect(
            self._show_nvidia_dxvk_vkd3d_choice_safe
        )
        self.prompt_affinity_install_signal.connect(self._prompt_affinity_install)
        self.install_application_signal.connect(self.install_application)
        self.show_spinner_signal.connect(self._show_spinner_safe)
        self.hide_spinner_signal.connect(self._hide_spinner_safe)
        self.waiting_for_gpu_selection = False
        self.gpu_selection_signal.connect(self._configure_gpu_selection_safe)
        step_start = log_timing("Signal connections", step_start)

        self.create_ui()
        step_start = log_timing("Create UI", step_start)

        self.apply_theme()
        step_start = log_timing("Apply theme", step_start)

        self.center_window()
        step_start = log_timing("Center window", step_start)

        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Affinity Linux Installer - Ready", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        step_start = log_timing("Defer slow operations", step_start)

        total_time = time.time() - startup_start
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )
        self.log("Startup Performance:", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )
        for step_name, elapsed in timing_log:
            percentage = (elapsed / total_time * 100) if total_time > 0 else 0
            self.log(
                f"  {step_name:.<30} {elapsed:>6.3f}s ({percentage:>5.1f}%)", "info"
            )
        self.log(f"  {'TOTAL STARTUP TIME':.<30} {total_time:>6.3f}s", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )

        self.log("Welcome! Please use the buttons on the right to get started.", "info")

        system_specs = self._get_system_specs()
        if system_specs:
            self.log("", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "info",
            )
            self.log("System Specifications:", "info")
            for spec in system_specs:
                self.log(f"  {spec}", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "info",
            )

            if self.log_file:
                try:
                    self.log_file.write(f"\nSystem Specifications:\n")
                    for spec in system_specs:
                        self.log_file.write(f"  {spec}\n")
                    self.log_file.write(f"{'=' * 80}\n")
                    self.log_file.flush()
                except Exception:
                    pass

        from PyQt6.QtCore import QTimer

        QTimer.singleShot(50, self._deferred_startup_tasks)
        QTimer.singleShot(500, self._check_and_update_dxvk_vkd3d)

    def _deferred_startup_tasks(self):
        """Run slow startup tasks in background after window is shown"""
        self.load_affinity_icon()

        self.setup_zoom()

        def run_background_tasks():
            import time as time_module

            bg_start = time_module.time()

            icons_start = time_module.time()
            self._ensure_icons_directory()
            icons_time = time_module.time() - icons_start
            if icons_time > 0.1:
                QTimer.singleShot(100, self._update_button_icons)

            patcher_start = time_module.time()
            self.ensure_patcher_files(silent=True)
            patcher_time = time_module.time() - patcher_start

            status_start = time_module.time()
            self.check_installation_status()
            status_time = time_module.time() - status_start

            total_bg_time = time_module.time() - bg_start

            if icons_time > 0.1 or patcher_time > 0.1 or status_time > 0.1:
                self.log(
                    f"Background tasks completed: icons={icons_time:.3f}s, patcher={patcher_time:.3f}s, status={status_time:.3f}s, total={total_bg_time:.3f}s",
                    "info",
                )

            wine_path = self.get_wine_path("wine")
            if not wine_path.exists():
                self.log(
                    "Click 'Setup Wine Environment' or 'One-Click Full Setup' to begin.",
                    "info",
                )
            else:
                self.log(
                    "Wine is set up. Use 'Update Affinity Applications' to install or update apps.",
                    "info",
                )

        threading.Thread(target=run_background_tasks, daemon=True).start()

    def check_installation_status(self):
        self.update_switch_backend_button()
        """Check if Wine and Affinity applications are installed, and update button states"""
        wine = self.get_wine_path("wine")
        wine_staging = self.get_wine_path("wine-staging")

        # Check if either wine or wine-staging exists
        wine_exists = wine.exists() or wine_staging.exists()

        wine_version_display = "Wine"
        if wine_exists:
            # Try both wine and wine-staging binaries
            for wine_bin in [wine, wine_staging]:
                if wine_bin.exists():
                    try:
                        success, stdout, _ = self.run_command(
                            [str(wine_bin), "--version"], check=False, capture=True
                        )
                        if success and stdout:
                            version_match = re.search(r"wine-(\d+\.\d+)", stdout)
                            if version_match:
                                wine_version_display = f"Wine {version_match.group(1)}"
                                break  # Found a working wine binary, no need to check further
                            else:
                                wine_dir = Path(self.directory) / "ElementalWarriorWine"
                                if (wine_dir / "bin" / "wine").exists():
                                    wine_version_display = "Wine (patched)"
                                    break
                    except Exception:
                        continue

            # If we still haven't found a version, mark as patched
            if wine_version_display == "Wine":
                wine_version_display = "Wine (patched)"

        if hasattr(self, "system_status_label"):
            if wine_exists:
                self.system_status_label.setStyleSheet(
                    "font-size: 12px; color: #4ec9b0; background-color: transparent; border: none; padding: 0px;"
                )
                self.system_status_label.setToolTip(
                    f"System Status: Ready - {wine_version_display} is installed"
                )
                if hasattr(self, "status_text_label"):
                    self.status_text_label.setText("Ready")
            else:
                self.system_status_label.setStyleSheet(
                    "font-size: 12px; color: #f48771; background-color: transparent; border: none; padding: 0px;"
                )
                self.system_status_label.setToolTip(
                    "System Status: Not Ready - Wine needs to be installed"
                )
                if hasattr(self, "status_text_label"):
                    self.status_text_label.setText("Not Ready")

        if wine_exists:
            self.log(f"Wine: ✓ Installed ({wine_version_display})", "success")
        else:
            self.log("Wine: ✗ Not installed", "error")

        app_status = {}
        app_names_display = {
            "Add": "Affinity (Unified)",
            "Photo": "Affinity Photo",
            "Designer": "Affinity Designer",
            "Publisher": "Affinity Publisher",
        }
        app_dirs = {
            "Add": ("Affinity", "Affinity.exe"),
            "Photo": ("Photo 2", "Photo.exe"),
            "Designer": ("Designer 2", "Designer.exe"),
            "Publisher": ("Publisher 2", "Publisher.exe"),
        }

        self.log("Affinity Applications:", "info")
        for app_name, (dir_name, exe_name) in app_dirs.items():
            app_path = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / dir_name
                / exe_name
            )
            is_installed = app_path.exists()
            app_status[app_name] = is_installed

            display_name = app_names_display.get(app_name, app_name)
            if is_installed:
                self.log(f"  {display_name}: ✓ Installed", "success")
            else:
                self.log(f"  {display_name}: ✗ Not installed", "error")

            if app_name in self.update_buttons:
                btn = self.update_buttons[app_name]
                if is_installed:
                    current_text = btn.text()
                    if "✓" not in current_text:
                        btn.setText(current_text.split("✓")[0].strip() + " ✓")
                    btn.setEnabled(True)

        self.log("System Dependencies:", "info")
        deps = ["wine", "winetricks", "wget", "curl", "7z", "tar", "jq"]
        deps_installed = True
        for dep in deps:
            if self.check_command(dep):
                self.log(f"  {dep}: ✓ Installed", "success")
            else:
                self.log(f"  {dep}: ✗ Not installed", "error")
                deps_installed = False

        if self.check_command("unzstd") or self.check_command("zstd"):
            self.log(f"  zstd: ✓ Installed", "success")
        else:
            self.log(f"  zstd: ✗ Not installed (optional)", "warning")

        if self.check_command("xz") or self.check_command("unxz"):
            self.log(f"  xz: ✓ Installed", "success")
        else:
            self.log(
                f"  xz: ✗ Not installed (optional - Python lzma will be used)",
                "warning",
            )

        if self.check_dotnet_sdk():
            self.log(f"  .NET SDK: ✓ Installed", "success")
        else:
            self.log(f"  .NET SDK: ✗ Not installed", "error")

        if wine_exists:
            self.log("Winetricks Dependencies:", "info")
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            wine = self.get_wine_path("wine")

            winetricks_components = [
                ("dotnet35sp1", ".NET Framework 3.5 SP1"),
                ("dotnet48", ".NET Framework 4.8"),
                ("corefonts", "Windows Core Fonts"),
                ("vcrun2022", "Visual C++ Redistributables 2022"),
                ("msxml3", "MSXML 3.0"),
                ("msxml6", "MSXML 6.0"),
                ("crypt32", "Cryptographic API 32"),
            ]

            for component, description in winetricks_components:
                if self._check_winetricks_component(component, wine, env):
                    self.log(f"  {description}: ✓ Installed", "success")
                else:
                    self.log(f"  {description}: ✗ Not installed", "error")

            try:
                success, stdout, _ = self.run_command(
                    [
                        str(wine),
                        "reg",
                        "query",
                        "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                    ],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success:
                    vulkan_set = False
                    try:
                        renderer_success, renderer_stdout, _ = self.run_command(
                            [
                                str(wine),
                                "reg",
                                "query",
                                "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                                "/v",
                                "renderer",
                            ],
                            check=False,
                            env=env,
                            capture=True,
                        )
                        if renderer_success and "vulkan" in renderer_stdout.lower():
                            vulkan_set = True
                    except Exception:
                        pass

                    if vulkan_set:
                        self.log(f"  Vulkan Renderer: ✓ Configured", "success")
                    else:
                        self.log(f"  Vulkan Renderer: ⚠ Not configured", "warning")
                else:
                    self.log(f"  Vulkan Renderer: ✗ Not configured", "error")
            except Exception:
                self.log(f"  Vulkan Renderer: ✗ Not configured", "error")

            self.log("WebView2 Runtime:", "info")
            if self.check_webview2_installed():
                self.log(f"  Microsoft Edge WebView2 Runtime: ✓ Installed", "success")
            else:
                self.log(f"  Microsoft Edge WebView2 Runtime: ✗ Not installed", "error")

        self.log("", "info")

        for app_name, button in self.update_buttons.items():
            if button is None:
                continue

            is_installed = app_status.get(app_name, False)
            enabled = wine_exists and is_installed

            button.setEnabled(enabled)
            if enabled:
                button.setStyleSheet("")

    def center_window(self):
        """Center window on screen"""
        frame = self.frameGeometry()
        screen = self.screen().availableGeometry().center()
        frame.moveCenter(screen)
        self.move(frame.topLeft())

    def setup_zoom(self):
        """Setup zoom in/out functionality for log area"""
        zoom_in_shortcut = QShortcut(QKeySequence("Ctrl+Plus"), self)
        zoom_in_shortcut.activated.connect(self.zoom_in)
        zoom_in_shortcut_alt = QShortcut(QKeySequence("Ctrl+="), self)
        zoom_in_shortcut_alt.activated.connect(self.zoom_in)

        zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+Minus"), self)
        zoom_out_shortcut.activated.connect(self.zoom_out)
        zoom_out_shortcut_alt = QShortcut(QKeySequence("Ctrl+-"), self)
        zoom_out_shortcut_alt.activated.connect(self.zoom_out)

        zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        zoom_reset_shortcut.activated.connect(self.zoom_reset)

    def zoom_in(self):
        """Zoom in (increase font size)"""
        if not hasattr(self, "log_text") or not self.log_text:
            return

        new_size = min(self.log_font_size + 1, 48)
        if new_size != self.log_font_size:
            self.log_font_size = new_size
            font = QFont("Consolas", self.log_font_size)
            self.log_text.setFont(font)
            self.log_text.document().setDefaultFont(font)
            self.update_zoom_buttons()

    def zoom_out(self):
        """Zoom out (decrease font size)"""
        if not hasattr(self, "log_text") or not self.log_text:
            return

        new_size = max(self.log_font_size - 1, 6)
        if new_size != self.log_font_size:
            self.log_font_size = new_size
            font = QFont("Consolas", self.log_font_size)
            self.log_text.setFont(font)
            self.log_text.document().setDefaultFont(font)
            self.update_zoom_buttons()

    def zoom_reset(self):
        """Reset zoom to default size"""
        if not hasattr(self, "log_text") or not self.log_text:
            return

        self.log_font_size = 11
        font = QFont("Consolas", 11)
        self.log_text.setFont(font)
        self.log_text.document().setDefaultFont(font)
        self.update_zoom_buttons()

    def update_zoom_buttons(self):
        """Update zoom button states"""
        try:
            if hasattr(self, "log_text") and self.log_text:
                current_font = self.log_text.currentFont()
                current_size = (
                    current_font.pointSize() if current_font else self.log_font_size
                )

                if hasattr(self, "zoom_in_btn"):
                    self.zoom_in_btn.setEnabled(current_size < 48)
                if hasattr(self, "zoom_out_btn"):
                    self.zoom_out_btn.setEnabled(current_size > 6)
        except Exception:
            pass

    def get_icon_path(self, icon_name):
        """Get the path to a light or dark icon based on theme"""
        if not icon_name:
            return None

        theme_suffix = "light" if self.dark_mode else "dark"

        icons_dir = (
            Path.home() / ".config" / "AffinityOnLinux" / "AffinityScripts" / "icons"
        )

        themed_icon_path = icons_dir / f"{icon_name}-{theme_suffix}.svg"
        if themed_icon_path.exists():
            return themed_icon_path

        base_icon_path = icons_dir / f"{icon_name}.svg"
        if base_icon_path.exists():
            return base_icon_path

        local_icons_dir = Path(__file__).parent / "icons"
        if local_icons_dir.exists():
            local_themed_icon = local_icons_dir / f"{icon_name}-{theme_suffix}.svg"
            if local_themed_icon.exists():
                return local_themed_icon

            local_base_icon = local_icons_dir / f"{icon_name}.svg"
            if local_base_icon.exists():
                return local_base_icon

        return None

    def _update_button_icons(self):
        """Update all button icons to match the current theme"""
        for btn, icon_name in self.icon_buttons:
            icon_path = self.get_icon_path(icon_name)
            if icon_path:
                icon = QIcon(str(icon_path))
                btn.setIcon(icon)

    def toggle_theme(self):
        """Toggle between dark and light themes"""
        self.dark_mode = not self.dark_mode
        self.apply_theme()

        if self.dark_mode:
            self.theme_toggle_btn.setText("☀")
            self.theme_toggle_btn.setToolTip("Switch to Light Mode")
        else:
            self.theme_toggle_btn.setText("🌙")
            self.theme_toggle_btn.setToolTip("Switch to Dark Mode")

        self._update_button_icons()

        self._update_top_bar_style()

        self._update_theme_button_style()

        self._update_right_scroll_style()

        self._update_progress_label_style()

    def get_dialog_stylesheet(self):
        """Get the appropriate stylesheet for dialogs based on current theme - clean modern style"""
        if self.dark_mode:
            return """
                QDialog {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                    background-color: transparent;
                    border: none;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                    background-color: transparent;
                    border: none;
                }
                QLineEdit {
                    background-color: #3c3c3c;
                    color: #dcdcdc;
                    border: 1px solid #555555;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus {
                    border: 1px solid #4ec9b0;
                    background-color: #3d3d3d;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton, QPushButton#primaryButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover, QPushButton#primaryButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed, QPushButton#primaryButton:pressed {
                    background-color: #3db9a0;
                }
                QDialogButtonBox QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QDialogButtonBox QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QDialogButtonBox QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QSlider::groove:horizontal {
                    background-color: #3c3c3c;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background-color: #4ec9b0;
                    width: 18px;
                    height: 18px;
                    margin: -6px 0;
                    border-radius: 9px;
                }
                QSlider::handle:horizontal:hover {
                    background-color: #5dd9c0;
                }
                QSlider::sub-page:horizontal {
                    background-color: #4ec9b0;
                    border-radius: 3px;
                }
                QSlider::add-page:horizontal {
                    background-color: #3c3c3c;
                    border-radius: 3px;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #2d2d2d;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #666666;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        else:
            return """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                    background-color: transparent;
                    border: none;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                    background-color: transparent;
                    border: none;
                }
                QLineEdit {
                    background-color: #ffffff;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus {
                    border: 1px solid #4caf50;
                    background-color: #fafafa;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 14px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#okButton, QPushButton#primaryButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#okButton:hover, QPushButton#primaryButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#okButton:pressed, QPushButton#primaryButton:pressed {
                    background-color: #3d8b40;
                }
                QDialogButtonBox QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QDialogButtonBox QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QDialogButtonBox QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QSlider::groove:horizontal {
                    background-color: #e0e0e0;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background-color: #4caf50;
                    width: 18px;
                    height: 18px;
                    margin: -6px 0;
                    border-radius: 9px;
                }
                QSlider::handle:horizontal:hover {
                    background-color: #45a049;
                }
                QSlider::sub-page:horizontal {
                    background-color: #4caf50;
                    border-radius: 3px;
                }
                QSlider::add-page:horizontal {
                    background-color: #e0e0e0;
                    border-radius: 3px;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """

    def get_messagebox_stylesheet(self):
        """Get the appropriate stylesheet for message boxes based on current theme - clean modern style"""
        if self.dark_mode:
            return """
                QMessageBox {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QMessageBox QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                    font-size: 13px;
                    line-height: 1.4;
                }
                QMessageBox QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QMessageBox QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QMessageBox QPushButton[default="true"] {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QMessageBox QPushButton[default="true"]:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QMessageBox QPushButton[default="true"]:pressed {
                    background-color: #3db9a0;
                }
            """
        else:
            return """
                QMessageBox {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QMessageBox QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                    font-size: 13px;
                    line-height: 1.4;
                }
                QMessageBox QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QMessageBox QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QMessageBox QPushButton[default="true"] {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QMessageBox QPushButton[default="true"]:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QMessageBox QPushButton[default="true"]:pressed {
                    background-color: #3d8b40;
                }
            """

    def apply_theme(self):
        """Apply current theme (dark or light)"""
        if self.dark_mode:
            self._apply_dark_theme()
        else:
            self._apply_light_theme()

    def _apply_dark_theme(self):
        """Apply modern dark theme with card-based design"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            QWidget {
                background-color: #1a1a1a;
                color: #e0e0e0;
                font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
            }
            /* Top Bar */
            QFrame#topBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a2a, stop:1 #1f1f1f);
                border-bottom: 2px solid #333333;
            }
            QLabel#titleLabel {
                font-size: 20px;
                font-weight: 600;
                color: #ffffff;
                letter-spacing: -0.5px;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusIndicator {
                font-size: 12px;
                color: #666666;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusText {
                font-size: 12px;
                color: #999999;
                font-weight: 500;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#themeToggle {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 8px;
                font-size: 18px;
            }
            QPushButton#themeToggle:hover {
                background-color: #3d3d3d;
                border-color: #555555;
            }
            /* Content Area */
            QWidget#contentArea {
                background-color: #1a1a1a;
            }
            /* Status Card */
            QFrame#statusCard {
                background-color: #252525;
                border: 1px solid #333333;
                border-radius: 12px;
            }
            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: 600;
                color: #ffffff;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            /* Progress Section */
            QFrame#progressSection {
                background-color: #1e1e1e;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                padding: 12px;
            }
            QLabel#progressLabel {
                font-size: 12px;
                font-weight: 500;
                color: #b0b0b0;
                padding: 8px 12px;
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
            QProgressBar#progressBar {
                border: none;
                background-color: #1a1a1a;
                height: 8px;
                border-radius: 4px;
            }
            QProgressBar#progressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4ec9b0, stop:1 #5dd9c0);
                border-radius: 4px;
            }
            QPushButton#cancelButton {
                background-color: #d32f2f;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#cancelButton:hover {
                background-color: #e53935;
            }
            QPushButton#cancelButton:pressed {
                background-color: #b71c1c;
            }
            /* Log Section */
            QFrame#logSection {
                background-color: #1e1e1e;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                padding: 12px;
            }
            QFrame#zoomToolbar {
                background-color: transparent;
                border: none;
            }
            QPushButton#zoomButton {
                background-color: #2d2d2d;
                color: #b0b0b0;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
            }
            QPushButton#zoomButton:hover {
                background-color: #3a3a3a;
                border-color: #4a4a4a;
                color: #ffffff;
            }
            QPushButton#zoomButton:disabled {
                background-color: #252525;
                color: #555555;
                border-color: #2d2d2d;
            }
            QTextEdit#logText {
                background-color: #0d0d0d;
                color: #d4d4d4;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                padding: 12px;
                selection-background-color: #007acc;
            }
            /* Button Cards */
            QFrame#buttonCard {
                background-color: #252525;
                border: 1px solid #333333;
                border-radius: 12px;
            }
            QPushButton#actionButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                padding: 12px 16px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                min-width: 200px;
            }
            QPushButton#actionButton:hover {
                background-color: #353535;
                border-color: #4d4d4d;
                color: #ffffff;
            }
            QPushButton#actionButton:pressed {
                background-color: #252525;
                border-color: #3d3d3d;
            }
            QPushButton#actionButton:disabled {
                background-color: #1f1f1f;
                color: #555555;
                border-color: #2d2d2d;
            }
            QPushButton#actionButton[class="primary"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4ec9b0, stop:1 #3db9a0);
                color: #000000;
                font-weight: 600;
                font-size: 14px;
                border: none;
            }
            QPushButton#actionButton[class="primary"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5dd9c0, stop:1 #4ec9b0);
            }
            QPushButton#actionButton[class="primary"]:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3db9a0, stop:1 #2da990);
            }
            /* Scroll Area */
            QScrollArea#rightScroll {
                background-color: #1a1a1a;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #3d3d3d;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4d4d4d;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QToolTip {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444444;
                padding: 6px;
                border-radius: 6px;
                font-size: 11px;
            }
            QDialog {
                background-color: #252525;
                border-radius: 12px;
            }
            QDialog QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#titleLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#descriptionLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QMessageBox {
                background-color: #252525;
                border-radius: 12px;
            }
            QMessageBox QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)

    def _apply_light_theme(self):
        """Apply modern light theme with card-based design"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f7;
            }
            QWidget {
                background-color: #f5f5f7;
                color: #1d1d1f;
                font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
            }
            /* Top Bar */
            QFrame#topBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f5f5f7);
                border-bottom: 2px solid #e0e0e0;
            }
            QLabel#titleLabel {
                font-size: 20px;
                font-weight: 600;
                color: #1d1d1f;
                letter-spacing: -0.5px;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusIndicator {
                font-size: 12px;
                color: #86868b;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusText {
                font-size: 12px;
                color: #515154;
                font-weight: 500;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#themeToggle {
                background-color: #e5e5e7;
                color: #1d1d1f;
                border: 1px solid #d0d0d0;
                border-radius: 8px;
                font-size: 18px;
            }
            QPushButton#themeToggle:hover {
                background-color: #d5d5d7;
                border-color: #c0c0c0;
            }
            /* Content Area */
            QWidget#contentArea {
                background-color: #f5f5f7;
            }
            /* Status Card */
            QFrame#statusCard {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: 600;
                color: #1d1d1f;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            /* Progress Section */
            QFrame#progressSection {
                background-color: #fafafa;
                border: 1px solid #e5e5e7;
                border-radius: 8px;
                padding: 12px;
            }
            QLabel#progressLabel {
                font-size: 12px;
                font-weight: 500;
                color: #515154;
                padding: 8px 12px;
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
            QProgressBar#progressBar {
                border: none;
                background-color: #e5e5e7;
                height: 8px;
                border-radius: 4px;
            }
            QProgressBar#progressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #34c759, stop:1 #30d158);
                border-radius: 4px;
            }
            QPushButton#cancelButton {
                background-color: #ff3b30;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#cancelButton:hover {
                background-color: #ff453a;
            }
            QPushButton#cancelButton:pressed {
                background-color: #d70015;
            }
            /* Log Section */
            QFrame#logSection {
                background-color: #fafafa;
                border: 1px solid #e5e5e7;
                border-radius: 8px;
                padding: 12px;
            }
            QFrame#zoomToolbar {
                background-color: transparent;
                border: none;
            }
            QPushButton#zoomButton {
                background-color: #ffffff;
                color: #515154;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
            }
            QPushButton#zoomButton:hover {
                background-color: #f5f5f7;
                border-color: #c0c0c0;
                color: #1d1d1f;
            }
            QPushButton#zoomButton:disabled {
                background-color: #f5f5f7;
                color: #86868b;
                border-color: #e0e0e0;
            }
            QTextEdit#logText {
                background-color: #ffffff;
                color: #1d1d1f;
                border: 1px solid #e5e5e7;
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                padding: 12px;
                selection-background-color: #007aff;
            }
            /* Button Cards */
            QFrame#buttonCard {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
            QPushButton#actionButton {
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid #e5e5e7;
                padding: 12px 16px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                min-width: 200px;
            }
            QPushButton#actionButton:hover {
                background-color: #ffffff;
                border-color: #d0d0d0;
                color: #000000;
            }
            QPushButton#actionButton:pressed {
                background-color: #e5e5e7;
                border-color: #c0c0c0;
            }
            QPushButton#actionButton:disabled {
                background-color: #f5f5f7;
                color: #86868b;
                border-color: #e5e5e7;
            }
            QPushButton#actionButton[class="primary"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #34c759, stop:1 #30d158);
                color: #ffffff;
                font-weight: 600;
                font-size: 14px;
                border: none;
            }
            QPushButton#actionButton[class="primary"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #30d158, stop:1 #2dd45f);
            }
            QPushButton#actionButton[class="primary"]:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #28cd55, stop:1 #24c04f);
            }
            /* Scroll Area */
            QScrollArea#rightScroll {
                background-color: #f5f5f7;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #f5f5f7;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #d0d0d0;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #c0c0c0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QToolTip {
                background-color: #1d1d1f;
                color: #ffffff;
                border: 1px solid #2d2d2f;
                padding: 6px;
                border-radius: 6px;
                font-size: 11px;
            }
            QDialog {
                background-color: #ffffff;
                border-radius: 12px;
            }
            QDialog QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#titleLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#descriptionLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QMessageBox {
                background-color: #ffffff;
                border-radius: 12px;
            }
            QMessageBox QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)

    def _update_theme_button_style(self):
        """Update theme toggle button styling based on current theme"""
        pass

    def _update_top_bar_style(self):
        """Update top bar styling based on current theme"""
        pass

    def _update_right_scroll_style(self):
        """Update right scroll area styling based on current theme"""
        if hasattr(self, "right_scroll"):
            if self.dark_mode:
                self.right_scroll.setStyleSheet("""
                    QScrollArea {
                        background-color: #1c1c1c;
                        border: none;
                    }
                    QScrollBar:vertical {
                        background-color: #1c1c1c;
                        width: 12px;
                        border-radius: 6px;
                    }
                    QScrollBar::handle:vertical {
                        background-color: #3c3c3c;
                        border-radius: 6px;
                        min-height: 30px;
                    }
                    QScrollBar::handle:vertical:hover {
                        background-color: #4a4a4a;
                    }
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                        height: 0px;
                    }
                    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                        background: none;
                    }
                """)
            else:
                self.right_scroll.setStyleSheet("""
                    QScrollArea {
                        background-color: #f5f5f5;
                        border: none;
                    }
                    QScrollBar:vertical {
                        background-color: #f5f5f5;
                        width: 12px;
                        border-radius: 6px;
                    }
                    QScrollBar::handle:vertical {
                        background-color: #c0c0c0;
                        border-radius: 6px;
                        min-height: 30px;
                    }
                    QScrollBar::handle:vertical:hover {
                        background-color: #a0a0a0;
                    }
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                        height: 0px;
                    }
                    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                        background: none;
                    }
                """)

    def _update_progress_label_style(self):
        """Update progress label styling based on current theme"""
        if hasattr(self, "progress_label"):
            if self.dark_mode:
                self.progress_label.setStyleSheet(
                    "font-size: 11px; font-weight: 500; color: #dcdcdc; "
                    "padding: 5px 10px; background-color: transparent; border: none; border-radius: 0px;"
                )
            else:
                self.progress_label.setStyleSheet(
                    "font-size: 11px; font-weight: 500; color: #2d2d2d; "
                    "padding: 5px 10px; background-color: transparent; border: none; border-radius: 0px;"
                )

    def create_ui(self):
        """Create the modern user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            top_bar_height = 56
            top_bar_margin = 12
            top_bar_spacing = 12
            icon_size = 32
        else:
            top_bar_height = 64
            top_bar_margin = 24
            top_bar_spacing = 16
            icon_size = 40

        self.top_bar = QFrame()
        self.top_bar.setFixedHeight(top_bar_height)
        self.top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(top_bar_margin, 12, top_bar_margin, 12)
        top_bar_layout.setSpacing(top_bar_spacing)

        if hasattr(self, "affinity_icon_path") and self.affinity_icon_path:
            try:
                icon = QIcon(self.affinity_icon_path)
                self.setWindowIcon(icon)

                try:
                    svg_widget = QSvgWidget(self.affinity_icon_path)
                    svg_widget.setFixedSize(icon_size, icon_size)
                    svg_widget.setStyleSheet("background: transparent;")
                    top_bar_layout.addWidget(svg_widget)
                except Exception:
                    icon_label = QLabel()
                    pixmap = icon.pixmap(icon_size, icon_size)
                    if not pixmap.isNull():
                        icon_label.setPixmap(
                            pixmap.scaled(
                                icon_size,
                                icon_size,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )
                        icon_label.setFixedSize(icon_size, icon_size)
                        top_bar_layout.addWidget(icon_label)
            except Exception:
                pass

        self.title_label = QLabel("Affinity on Linux")
        self.title_label.setObjectName("titleLabel")
        if screen_width < 1024:
            self.title_label.setStyleSheet(
                "font-size: 18px; font-weight: 600; background-color: transparent; border: none; padding: 0px;"
            )
        else:
            self.title_label.setStyleSheet(
                "background-color: transparent; border: none; padding: 0px;"
            )
        top_bar_layout.addWidget(self.title_label)

        top_bar_layout.addStretch()

        status_container = QWidget()
        status_container.setStyleSheet("background-color: transparent; border: none;")
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)

        self.system_status_label = QLabel("●")
        self.system_status_label.setObjectName("statusIndicator")
        self.system_status_label.setToolTip("System Status: Initializing...")
        status_layout.addWidget(self.system_status_label)

        status_text = QLabel("Initializing...")
        status_text.setObjectName("statusText")
        if screen_width < 800:
            status_text.setVisible(False)
        status_layout.addWidget(status_text)
        self.status_text_label = status_text

        top_bar_layout.addWidget(status_container)

        self.theme_toggle_btn = QPushButton("☀")
        self.theme_toggle_btn.setObjectName("themeToggle")
        self.theme_toggle_btn.setToolTip("Switch Theme")
        self.theme_toggle_btn.setFixedSize(icon_size, icon_size)
        self.theme_toggle_btn.clicked.connect(self.toggle_theme)
        top_bar_layout.addWidget(self.theme_toggle_btn)

        main_layout.addWidget(self.top_bar)

        content_widget = QWidget()
        content_widget.setObjectName("contentArea")
        content_layout = QHBoxLayout(content_widget)

        if screen_width < 1024:
            content_spacing = 12
            content_margin = 12
            right_panel_min = 280
            right_panel_max = 320
        elif screen_width < 1280:
            content_spacing = 16
            content_margin = 16
            right_panel_min = 320
            right_panel_max = 380
        else:
            content_spacing = 20
            content_margin = 20
            right_panel_min = 360
            right_panel_max = 420

        content_layout.setSpacing(content_spacing)
        content_layout.setContentsMargins(
            content_margin, content_margin, content_margin, content_margin
        )

        left_panel = self.create_status_section()
        content_layout.addWidget(left_panel, stretch=2)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setObjectName("rightScroll")
        self.right_scroll = right_scroll
        self._update_right_scroll_style()

        right_panel = self.create_button_sections()
        right_scroll.setWidget(right_panel)
        right_scroll.setMinimumWidth(right_panel_min)
        right_scroll.setMaximumWidth(right_panel_max)

        content_layout.addWidget(right_scroll, stretch=1)

        main_layout.addWidget(content_widget, stretch=1)

    def create_status_section(self):
        """Create the modern status/log output section (responsive)"""
        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            card_spacing = 12
            card_margin = 12
        elif screen_width < 1280:
            card_spacing = 14
            card_margin = 16
        else:
            card_spacing = 16
            card_margin = 20

        card = QFrame()
        card.setObjectName("statusCard")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(card_spacing)
        card_layout.setContentsMargins(
            card_margin, card_margin, card_margin, card_margin
        )

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Status & Log")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()
        card_layout.addLayout(header)

        progress_section = QFrame()
        progress_section.setObjectName("progressSection")
        progress_layout = QVBoxLayout(progress_section)
        progress_layout.setSpacing(8)
        progress_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("progressLabel")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.progress_label)

        progress_container = QHBoxLayout()
        progress_container.setSpacing(12)
        progress_container.setContentsMargins(0, 0, 0, 0)

        self.progress = QProgressBar()
        self.progress.setObjectName("progressBar")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        progress_container.addWidget(self.progress, stretch=1)

        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setObjectName("cancelButton")
        self.cancel_btn.setToolTip("Cancel current operation")
        self.cancel_btn.setFixedSize(32, 32)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_operation)
        progress_container.addWidget(self.cancel_btn)

        progress_layout.addLayout(progress_container)
        card_layout.addWidget(progress_section)

        log_section = QFrame()
        log_section.setObjectName("logSection")
        log_layout = QVBoxLayout(log_section)
        log_layout.setSpacing(12)
        log_layout.setContentsMargins(0, 0, 0, 0)

        zoom_toolbar = QFrame()
        zoom_toolbar.setObjectName("zoomToolbar")
        zoom_layout = QHBoxLayout(zoom_toolbar)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(8)
        zoom_layout.addStretch()

        icon_name_zoom_out = "zoom-out"
        icon_path_zoom_out = self.get_icon_path(icon_name_zoom_out)
        self.zoom_out_btn = QPushButton()
        self.zoom_out_btn.setObjectName("zoomButton")
        self.zoom_out_btn.setToolTip("Zoom Out (Ctrl+-)")
        self.zoom_out_btn.setFixedSize(32, 32)
        if icon_path_zoom_out:
            self.zoom_out_btn.setIcon(QIcon(str(icon_path_zoom_out)))
        self.zoom_out_btn.setIconSize(QSize(18, 18))
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_layout.addWidget(self.zoom_out_btn)
        self.icon_buttons.append((self.zoom_out_btn, icon_name_zoom_out))

        icon_name_zoom_reset = "zoom-original"
        icon_path_zoom_reset = self.get_icon_path(icon_name_zoom_reset)
        self.zoom_reset_btn = QPushButton()
        self.zoom_reset_btn.setObjectName("zoomButton")
        self.zoom_reset_btn.setToolTip("Reset Zoom (Ctrl+0)")
        self.zoom_reset_btn.setFixedSize(32, 32)
        if icon_path_zoom_reset:
            self.zoom_reset_btn.setIcon(QIcon(str(icon_path_zoom_reset)))
        self.zoom_reset_btn.setIconSize(QSize(18, 18))
        self.zoom_reset_btn.clicked.connect(self.zoom_reset)
        zoom_layout.addWidget(self.zoom_reset_btn)
        self.icon_buttons.append((self.zoom_reset_btn, icon_name_zoom_reset))

        icon_name_zoom_in = "zoom-in"
        icon_path_zoom_in = self.get_icon_path(icon_name_zoom_in)
        self.zoom_in_btn = QPushButton()
        self.zoom_in_btn.setObjectName("zoomButton")
        self.zoom_in_btn.setToolTip("Zoom In (Ctrl++)")
        self.zoom_in_btn.setFixedSize(32, 32)
        if icon_path_zoom_in:
            self.zoom_in_btn.setIcon(QIcon(str(icon_path_zoom_in)))
        self.zoom_in_btn.setIconSize(QSize(18, 18))
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_layout.addWidget(self.zoom_in_btn)
        self.icon_buttons.append((self.zoom_in_btn, icon_name_zoom_in))

        log_layout.addWidget(zoom_toolbar)

        self.log_text = ZoomableTextEdit(self)
        self.log_text.setObjectName("logText")
        self.log_text.setReadOnly(True)
        min_font_size = max(9, self.log_font_size)
        self.log_text.setFont(QFont("Consolas", min_font_size))
        self.log_text.set_zoom_callbacks(self.zoom_in, self.zoom_out)
        screen = self.screen().availableGeometry()
        if screen.height() < 768:
            self.log_text.setMinimumHeight(150)
        else:
            self.log_text.setMinimumHeight(200)
        log_layout.addWidget(self.log_text)

        card_layout.addWidget(log_section)

        self.update_zoom_buttons()

        return card

    def create_button_sections(self):
        """Create modern organized button sections (responsive)"""
        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            container_spacing = 12
        elif screen_width < 1280:
            container_spacing = 14
        else:
            container_spacing = 16

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(container_spacing)
        container_layout.setContentsMargins(0, 0, 0, 0)

        quick_group = self.create_button_group(
            "Quick Start",
            [
                (
                    "One-Click Full Setup",
                    self.one_click_setup,
                    "Setup Wine, dependencies, and prepare for Affinity installation",
                    "rocket",
                ),
                (
                    "Setup Wine Environment",
                    self.setup_wine_environment,
                    "Download and configure Wine environment only",
                    "wine",
                ),
                (
                    "Install System Dependencies",
                    self.install_system_dependencies,
                    "Install required Linux packages",
                    "dependencies",
                ),
                (
                    "Install Winetricks Dependencies",
                    self.install_winetricks_deps,
                    "Install Windows components (.NET, fonts, etc.)",
                    "wand",
                ),
            ],
        )
        container_layout.addWidget(quick_group)

        sys_group = self.create_button_group(
            "System Setup",
            [
                (
                    "Download Affinity Installer",
                    self.download_affinity_installer,
                    "Download the latest Affinity installer from official source",
                    "download",
                ),
                (
                    "Install from File Manager",
                    self.install_from_file,
                    "Install Affinity or any Windows app from a local .exe file",
                    "folderopen",
                ),
            ],
        )
        container_layout.addWidget(sys_group)

        app_buttons = [
            (
                "Affinity (Unified)",
                "Add",
                "Update or install Affinity V3 unified application",
                "affinity-unified",
            ),
            (
                "Affinity Photo",
                "Photo",
                "Update or install Affinity Photo for image editing",
                "camera",
            ),
            (
                "Affinity Designer",
                "Designer",
                "Update or install Affinity Designer for vector graphics",
                "pen",
            ),
            (
                "Affinity Publisher",
                "Publisher",
                "Update or install Affinity Publisher for page layout",
                "book",
            ),
        ]
        app_group = self.create_button_group(
            "Update Affinity Applications",
            [
                (
                    text,
                    lambda name=app_name: self.update_application(name),
                    tooltip,
                    icon,
                )
                for text, app_name, tooltip, icon in app_buttons
            ],
            button_refs=self.update_buttons,
            button_keys=[app_name for _, app_name, _, _ in app_buttons],
        )
        container_layout.addWidget(app_group)

        troubleshoot_group = self.create_button_group(
            "Troubleshooting",
            [
                (
                    "Switch Wine Version",
                    self.switch_wine_version,
                    "Remove current Wine and install a different version (keeps your apps and settings)",
                    "wine",
                ),
                (
                    "Wine Configuration",
                    self.open_winecfg,
                    "Open Wine settings to configure Windows version and libraries",
                    "wine",
                ),
                (
                    "Winetricks",
                    self.open_winetricks,
                    "Install additional Windows components and dependencies",
                    "wand",
                ),
                (
                    "Set Windows 11 + Renderer",
                    self.set_windows11_renderer,
                    "Configure Windows version and graphics renderer (Vulkan/OpenGL)",
                    "windows",
                ),
                (
                    "GPU Selection",
                    self.configure_gpu_selection,
                    "Select which GPU to use for dual GPU setups",
                    "display",
                ),
                (
                    self.get_switch_backend_button_text(),
                    self.switch_graphics_backend,
                    self.get_switch_backend_tooltip(),
                    "lightning",
                ),
                (
                    "Reinstall WinMetadata",
                    self.reinstall_winmetadata,
                    "Fix corrupted Windows metadata files",
                    "loop",
                ),
                (
                    "WebView2 Runtime (v3)",
                    self.install_webview2_runtime,
                    "Install WebView2 for Affinity V3 Help system",
                    "chrome",
                ),
                (
                    "Fix Settings (v3)",
                    self.fix_affinity_settings,
                    "Patch Affinity v3 DLL to enable settings saving",
                    "cog",
                ),
                (
                    "Set DPI Scaling",
                    self.set_dpi_scaling,
                    "Adjust interface size for better readability",
                    "scale",
                ),
                (
                    "Uninstall",
                    self.uninstall_affinity_linux,
                    "Completely remove Affinity Linux installation",
                    "trash",
                ),
            ],
        )
        container_layout.addWidget(troubleshoot_group)

        patches_group = self.create_button_group(
            "Patches",
            [
                (
                    "Return Colors (v3)",
                    self.apply_return_colors,
                    "Restore colored icons in Affinity v3 (replaces monochrome icons with v2 colored icons). Requires .NET SDK 10.0+",
                    "wand",
                ),
                (
                    "Install AffinityPluginLoader",
                    self.install_affinity_plugin_loader,
                    "Download and install the latest AffinityPluginLoader + WineFix from GitHub. Also updates Affinity.desktop to launch via AffinityHook.exe",
                    "wand",
                ),
                (
                    "Patch OpenCL (GPU Acceleration)",
                    self.apply_opencl_patches,
                    "Install Wine OpenCL fix and patch libraster.dll for GPU-accelerated filters. Tested on AMD GPUs.",
                    "wand",
                ),
                (
                    "Enable Canva Login",
                    self.setup_canva_login,
                    "Set up TLS relay and OAuth patches for Canva sign-in. Requires socat and .NET SDK 8.0+",
                    "chrome",
                ),
            ],
        )
        container_layout.addWidget(patches_group)

        launch_group = self.create_button_group(
            "Launch",
            [
                (
                    "Launch Affinity v3",
                    self.launch_affinity_v3,
                    "Start Affinity V3 unified application",
                    "play",
                ),
            ],
        )
        container_layout.addWidget(launch_group)

        other_group = self.create_button_group(
            "Other",
            [
                ("Exit", self.close, "Close the installer", "exit"),
            ],
        )
        container_layout.addWidget(other_group)

        container_layout.addStretch()

        return container

    def create_button_group(self, title, buttons, button_refs=None, button_keys=None):
        """Create a modern grouped button section (responsive)"""
        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            card_spacing = 8
            card_margin = 12
            button_height = 40
            icon_size = 18
        elif screen_width < 1280:
            card_spacing = 10
            card_margin = 14
            button_height = 42
            icon_size = 20
        else:
            card_spacing = 12
            card_margin = 16
            button_height = 44
            icon_size = 22

        card = QFrame()
        card.setObjectName("buttonCard")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(card_spacing)
        card_layout.setContentsMargins(card_margin, 16, card_margin, card_margin)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        if screen_width < 1024:
            title_label.setStyleSheet(
                "font-size: 14px; font-weight: 600; background-color: transparent; border: none; padding: 0px;"
            )
        else:
            title_label.setStyleSheet(
                "background-color: transparent; border: none; padding: 0px;"
            )
        card_layout.addWidget(title_label)

        buttons_layout = QVBoxLayout()
        if screen_width < 1024:
            buttons_layout.setSpacing(6)
        else:
            buttons_layout.setSpacing(8)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        for idx, button_data in enumerate(buttons):
            tooltip = None
            icon_name = None
            if len(button_data) == 2:
                text, command = button_data
            elif len(button_data) == 3:
                text, command, tooltip = button_data
            elif len(button_data) == 4:
                text, command, tooltip, icon_name = button_data
            else:
                text, command = button_data[0], button_data[1]

            btn = QPushButton(text)
            btn.setObjectName("actionButton")

            if text == "One-Click Full Setup":
                btn.setProperty("class", "primary")

            btn.clicked.connect(
                lambda checked=False, b=btn, cmd=command: self._handle_button_click(
                    b, cmd
                )
            )

            if icon_name:
                icon_path = self.get_icon_path(icon_name)
                if icon_path:
                    icon = QIcon(str(icon_path))
                    btn.setIcon(icon)
                    btn.setIconSize(QSize(icon_size, icon_size))
                    self.icon_buttons.append((btn, icon_name))

            if tooltip:
                btn.setToolTip(tooltip)

            btn.setMinimumHeight(button_height)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if screen_width < 800:
                btn.setMinimumWidth(220)
            elif screen_width < 1024:
                btn.setMinimumWidth(240)
            else:
                btn.setMinimumWidth(260)

            buttons_layout.addWidget(btn)

            if (
                button_refs is not None
                and button_keys is not None
                and idx < len(button_keys)
            ):
                button_refs[button_keys[idx]] = btn

            if text.startswith("Switch to"):
                self.switch_backend_button = btn

        card_layout.addLayout(buttons_layout)

        return card

    def _handle_button_click(self, button, command):
        """Record last clicked button and invoke the original command."""
        try:
            self._last_clicked_button = button
            command()
        except Exception as e:
            self._last_clicked_button = None
            self.log(f"Error executing command: {e}", "error")

    def _show_spinner_safe(self, button):
        """Replace the given button's icon with a rotating spinner (UI thread)."""
        try:
            if button is None or not isinstance(button, QPushButton):
                return
            if button in self._button_spinner_map:
                return
            current_size = button.iconSize()
            size = (
                max(16, max(current_size.width(), current_size.height()))
                if current_size.isValid()
                else max(20, button.sizeHint().height() - 6)
            )
            color = QColor("#8ff361") if self.dark_mode else QColor("#4caf50")
            state = {
                "angle": 0,
                "timer": QTimer(self),
                "orig_icon": button.icon(),
                "orig_size": current_size
                if current_size.isValid()
                else QSize(size, size),
                "size": size,
                "color": color,
            }

            def tick():
                state["angle"] = (state["angle"] - 30) % 360
                pm = QPixmap(state["size"], state["size"])
                pm.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                lw = max(2, int(state["size"] * 0.12))
                rect = pm.rect().adjusted(lw, lw, -lw, -lw)
                pen = QPen(state["color"])
                pen.setWidth(lw)
                painter.setPen(pen)
                start_angle = int(state["angle"] * 16)
                span_angle = int(270 * 16)
                painter.drawArc(rect, start_angle, span_angle)
                painter.end()
                button.setIcon(QIcon(pm))
                button.setIconSize(QSize(state["size"], state["size"]))

            t = state["timer"]
            t.setInterval(50)
            t.timeout.connect(tick)
            t.start()
            tick()
            self._button_spinner_map[button] = state
        except Exception:
            pass

    def _hide_spinner_safe(self, button):
        """Restore the button's original icon (UI thread)."""
        try:
            state = self._button_spinner_map.pop(button, None)
            if state is None:
                return
            timer = state.get("timer")
            if timer:
                try:
                    timer.stop()
                except Exception:
                    pass
            orig_icon = state.get("orig_icon")
            orig_size = state.get("orig_size")
            if isinstance(button, QPushButton):
                if orig_icon is not None:
                    button.setIcon(orig_icon)
                if orig_size is not None and orig_size.isValid():
                    button.setIconSize(orig_size)
        except Exception:
            pass

    def load_affinity_icon(self):
        """Load Affinity V3 icon (non-blocking - downloads in background if needed)"""
        self.affinity_icon_path = None

        def check_and_load_icon():
            try:
                icon_dir = Path.home() / ".local" / "share" / "icons"
                icon_dir.mkdir(parents=True, exist_ok=True)
                icon_path = icon_dir / "Affinity.svg"

                if icon_path.exists():
                    try:
                        with open(icon_path, "rb") as f:
                            first_bytes = f.read(100).decode("utf-8", errors="ignore")
                            if first_bytes.strip().startswith(
                                "<?xml"
                            ) or first_bytes.strip().startswith("<svg"):
                                self.affinity_icon_path = str(icon_path)
                                from PyQt6.QtCore import QTimer

                                QTimer.singleShot(
                                    0, lambda: self.setWindowIcon(QIcon(str(icon_path)))
                                )
                                return
                            else:
                                icon_path.unlink()
                    except Exception:
                        self.affinity_icon_path = str(icon_path)
                        from PyQt6.QtCore import QTimer

                        QTimer.singleShot(
                            0, lambda: self.setWindowIcon(QIcon(str(icon_path)))
                        )
                        return

                try:
                    icon_url = "https://raw.githubusercontent.com/seapear/AffinityOnLinux/main/Assets/Icons/Affinity-Canva.svg"
                    urllib.request.urlretrieve(icon_url, str(icon_path))
                    self.affinity_icon_path = str(icon_path)
                    from PyQt6.QtCore import QTimer

                    QTimer.singleShot(
                        0, lambda: self.setWindowIcon(QIcon(str(icon_path)))
                    )
                except Exception:
                    pass
            except Exception:
                pass

        threading.Thread(target=check_and_load_icon, daemon=True).start()

    def closeEvent(self, event):
        """Handle window close event - close log file"""
        if self.log_file:
            try:
                log_footer = f"{'=' * 80}\n"
                log_footer += f"Session Ended: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                log_footer += f"{'=' * 80}\n\n"
                self.log_file.write(log_footer)
                self.log_file.close()
            except Exception:
                pass
        event.accept()

    def sanitize_filename(self, filename):
        """Sanitize filename by replacing spaces and other problematic characters"""
        sanitized = filename.replace(" ", "-")
        sanitized = sanitized.replace("(", "-").replace(")", "-")
        sanitized = sanitized.replace("[", "-").replace("]", "-")
        while "--" in sanitized:
            sanitized = sanitized.replace("--", "-")
        return sanitized

    def log(self, message, level="info"):
        """Add message to log (thread-safe via signal)"""
        self.log_signal.emit(message, level)

    def _get_system_specs(self):
        """Gather system specifications"""
        specs = []

        try:
            uname = platform.uname()
            specs.append(f"OS: {uname.system} {uname.release}")
            specs.append(f"Architecture: {uname.machine}")
        except Exception:
            pass

        try:
            distro_info = {}
            if Path("/etc/os-release").exists():
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if "=" in line:
                            key, value = line.strip().split("=", 1)
                            distro_info[key] = value.strip('"')
            if "PRETTY_NAME" in distro_info:
                specs.append(f"Distribution: {distro_info['PRETTY_NAME']}")
            elif "NAME" in distro_info:
                version = distro_info.get("VERSION_ID", "")
                specs.append(f"Distribution: {distro_info['NAME']} {version}".strip())
        except Exception:
            pass

        try:
            cpu_info = ""
            if Path("/proc/cpuinfo").exists():
                with open("/proc/cpuinfo", "r") as f:
                    cpu_info = f.read()

            if cpu_info:
                for line in cpu_info.split("\n"):
                    if "model name" in line.lower():
                        cpu_model = line.split(":", 1)[1].strip()
                        specs.append(f"CPU: {cpu_model}")
                        break

                cpu_count = cpu_info.count("processor")
                if cpu_count > 0:
                    specs.append(f"CPU Cores: {cpu_count}")
        except Exception:
            pass

        try:
            mem_info = ""
            if Path("/proc/meminfo").exists():
                with open("/proc/meminfo", "r") as f:
                    mem_info = f.read()

            if mem_info:
                for line in mem_info.split("\n"):
                    if line.startswith("MemTotal:"):
                        mem_kb = int(line.split()[1])
                        mem_gb = mem_kb / (1024 * 1024)
                        specs.append(f"RAM: {mem_gb:.1f} GB")
                        break
        except Exception:
            pass

        try:
            gpu_info = []
            if Path("/proc/driver/nvidia/version").exists():
                try:
                    with open("/proc/driver/nvidia/version", "r") as f:
                        nvidia_version = f.read().strip()
                        gpu_info.append(
                            f"NVIDIA Driver: {nvidia_version.split()[7] if len(nvidia_version.split()) > 7 else 'Detected'}"
                        )
                except Exception:
                    pass

            try:
                result = subprocess.run(
                    ["lspci"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout:
                    for line in result.stdout.split("\n"):
                        if (
                            "vga" in line.lower()
                            or "3d" in line.lower()
                            or "display" in line.lower()
                        ):
                            gpu_line = line.split(":", 2)[-1].strip()
                            if gpu_line:
                                gpu_info.append(f"GPU: {gpu_line}")
                                break
            except Exception:
                pass

            if gpu_info:
                specs.extend(gpu_info)
        except Exception:
            pass

        return specs

    def _init_log_file(self):
        """Initialize log file"""
        try:
            self.log_file = open(self.log_file_path, "a", encoding="utf-8")
            log_header = f"\n{'=' * 80}\n"
            log_header += f"Affinity Linux Installer - Session Started\n"
            log_header += f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            log_header += f"{'=' * 80}\n"
            self.log_file.write(log_header)
            self.log_file.flush()
        except Exception as e:
            self.log_file = None

    def _log_safe(self, message, level="info"):
        """Thread-safe log handler (called from main thread)"""
        timestamp = time.strftime("%H:%M:%S")

        if level == "error":
            icon = "❌"
            color = "#ff7b72"
            bg_color = "rgba(255, 123, 114, 0.1)"
            icon_color = "#ff7b72"
        elif level == "success":
            icon = "✔"
            color = "#6a9955"
            bg_color = "rgba(106, 153, 85, 0.1)"
            icon_color = "#6a9955"
        elif level == "warning":
            icon = "⚠️"
            color = "#cd9731"
            bg_color = "rgba(205, 151, 49, 0.1)"
            icon_color = "#cd9731"
        else:
            icon = "•"
            color = "#9cdcfe"
            bg_color = "transparent"
            icon_color = "#569cd6"

        message = message.replace("<", "&lt;").replace(">", "&gt;")

        timestamp_html = (
            f'<span style="color: #6c7886; font-weight: 500;">[{timestamp}]</span>'
        )
        icon_html = f'<span style="color: {icon_color}; font-weight: bold; font-size: 12px;">{icon}</span>'

        if level in ["error", "success", "warning"]:
            full_message = f'<div style="background-color: {bg_color}; padding: 4px 8px; margin: 2px 0; border-radius: 4px; border-left: 3px solid {icon_color};">{timestamp_html} {icon_html} <span style="color: {color};">{message}</span></div>'
        else:
            full_message = f'<div style="padding: 2px 4px; margin: 1px 0;">{timestamp_html} {icon_html} <span style="color: {color};">{message}</span></div>'

        self.log_text.append(full_message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

        if self.log_file:
            try:
                plain_message = f"[{timestamp}] [{level.upper()}] {message}"
                self.log_file.write(plain_message + "\n")
                self.log_file.flush()
            except Exception:
                pass

    def update_progress(self, value):
        """Update progress bar (thread-safe via signal)"""
        self.progress_signal.emit(value)

    def _update_progress_safe(self, value):
        """Thread-safe progress update handler (called from main thread)"""
        self.progress.setValue(int(value * 100))

    def _update_progress_text_safe(self, text):
        """Thread-safe progress text update handler (called from main thread)"""
        self.progress_label.setText(text)

    def update_progress_text(self, text):
        """Update progress label text (thread-safe via signal)"""
        self.progress_text_signal.emit(text)

    def cancel_operation(self):
        """Cancel the current operation with confirmation"""
        reply = QMessageBox.question(
            self,
            "Cancel Operation",
            f"Are you sure you want to cancel the current operation?\n\n"
            f"Operation: {self.current_operation or 'Unknown'}\n\n"
            f"Note: This may leave the installation in an incomplete state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.operation_cancelled = True
            self.cancel_event.set()
            self.update_progress_text("Cancelling...")
            try:
                self.terminate_active_processes()
            except Exception:
                pass
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "warning",
            )
            self.log("⚠ Operation cancelled by user", "warning")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                "warning",
            )
            self.update_progress_text("Operation cancelled")
            self.update_progress(0.0)
            self.cancel_btn.setVisible(False)
            self.operation_in_progress = False
            try:
                if self._operation_button is not None:
                    self.hide_spinner_signal.emit(self._operation_button)
            except Exception:
                pass

    def start_operation(self, operation_name):
        """Mark the start of an operation and show cancel button"""
        self.operation_cancelled = False
        self.cancel_event.clear()
        self.current_operation = operation_name
        self.operation_in_progress = True
        if self._last_clicked_button is not None:
            self._operation_button = self._last_clicked_button
            self.show_spinner_signal.emit(self._operation_button)
        if hasattr(self, "cancel_btn"):
            self.cancel_btn.setVisible(True)

    def end_operation(self):
        """Mark the end of an operation: restore UI, reset progress, toggle cancel."""
        self.operation_in_progress = False
        self.current_operation = None
        if hasattr(self, "cancel_btn"):
            self.cancel_btn.setVisible(False)
        if self._operation_button is not None:
            self.hide_spinner_signal.emit(self._operation_button)
            self._operation_button = None
            self._last_clicked_button = None
        self.update_progress(0.0)
        self.update_progress_text("Ready")

    def check_cancelled(self):
        """Check if operation was cancelled"""
        if self.operation_cancelled:
            self.end_operation()
            return True
        return False

    def show_message(self, title, message, msg_type="info"):
        """Show message box (thread-safe via signal)"""
        self.show_message_signal.emit(title, message, msg_type)

    def _show_message_safe(self, title, message, msg_type="info"):
        """Thread-safe message box handler (called from main thread)"""
        msg_box = QMessageBox()
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStyleSheet(self.get_messagebox_stylesheet())

        if msg_type == "error":
            msg_box.setIcon(QMessageBox.Icon.Critical)
        elif msg_type == "warning":
            msg_box.setIcon(QMessageBox.Icon.Warning)
        else:
            msg_box.setIcon(QMessageBox.Icon.Information)

        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def _request_sudo_password_safe(self):
        """Request sudo password from user (called from main thread)"""
        dialog = QDialog()
        dialog.setWindowTitle("Administrator Authentication Required")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing - improved for all screen sizes
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(350, int(screen_width * 0.9))
            min_height = min(200, int(screen_height * 0.7))
            default_width = min(450, int(screen_width * 0.85))
            default_height = min(220, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 400
            min_height = 200
            default_width = 500
            default_height = 240
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 400
            min_height = 200
            default_width = 500
            default_height = 240
            max_width = 700
            max_height = 500

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        title_label = QLabel("Administrator Authentication Required")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        desc_label = QLabel(
            "This operation requires administrator privileges.\n\nPlease enter your password to continue:"
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_input.setPlaceholderText("Enter your password")
        password_input.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(password_input)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        password_input.returnPressed.connect(dialog.accept)

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        password_input.setFocus()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.sudo_password = password_input.text()
        else:
            self.sudo_password = None

    def get_sudo_password(self):
        """Get sudo password from user (thread-safe)"""
        if self.sudo_password_validated and self.sudo_password:
            return self.sudo_password

        self.sudo_password = None
        self.sudo_password_dialog_signal.emit()

        max_wait = 300
        waited = 0
        while self.sudo_password is None and waited < max_wait:
            time.sleep(0.1)
            waited += 1

        return self.sudo_password

    def validate_sudo_password(self, password):
        """Validate sudo password by running a test command"""
        try:
            env = os.environ.copy()
            env.pop("SUDO_ASKPASS", None)

            process = subprocess.Popen(
                ["sudo", "-S", "true"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                preexec_fn=os.setsid,
            )

            try:
                stdout, stderr = process.communicate(input=f"{password}\n", timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    if process.pid:
                        try:
                            pgid = os.getpgid(process.pid)
                            os.killpg(pgid, signal.SIGTERM)
                            time.sleep(0.5)
                            if process.poll() is None:
                                os.killpg(pgid, signal.SIGKILL)
                        except (ProcessLookupError, OSError, AttributeError):
                            process.kill()
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                try:
                    process.communicate()
                except Exception:
                    pass
                self.log(
                    "Password validation timed out - sudo may be waiting for input",
                    "error",
                )
                self.sudo_password_validated = False
                return False
            except Exception as e:
                try:
                    if process.poll() is None:
                        process.wait(timeout=1)
                except Exception:
                    pass
                if process.returncode == 0:
                    self.sudo_password_validated = True
                    return True
                self.log(f"Error validating sudo password: {e}", "error")
                self.sudo_password_validated = False
                return False

            if process.returncode == 0:
                self.sudo_password_validated = True
                return True
            else:
                # Check stderr for more details
                if stderr:
                    error_msg = stderr.strip()
                    if (
                        "incorrect password" in error_msg.lower()
                        or "sorry" in error_msg.lower()
                    ):
                        self.log("Incorrect password", "error")
                    else:
                        self.log(f"Password validation failed: {error_msg}", "error")
                else:
                    self.log("Password validation failed", "error")
                self.sudo_password_validated = False
                return False
        except Exception as e:
            self.log(f"Error validating sudo password: {e}", "error")
            self.sudo_password_validated = False
            return False

    def _request_interactive_response_safe(self, prompt_text, default_response):
        """Request user response to interactive prompt (called from main thread)"""
        # Parse the prompt to determine type
        prompt_lower = prompt_text.lower()

        # Detect yes/no questions
        if any(
            pattern in prompt_lower
            for pattern in ["(y/n)", "[y/n]", "yes/no", "overwrite?"]
        ):
            # Extract default from prompt
            default_yes = "y" in default_response.lower() if default_response else False

            reply = QMessageBox.question(
                self,
                "User Input Required",
                prompt_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
                if default_yes
                else QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.interactive_response = "y\n"
            else:
                self.interactive_response = "n\n"
        else:
            # For other prompts, use input dialog
            response, ok = QInputDialog.getText(
                self,
                "User Input Required",
                prompt_text,
                QLineEdit.EchoMode.Normal,
                default_response or "",
            )

            if ok:
                self.interactive_response = response + "\n"
            else:
                self.interactive_response = "\n"  # Empty response (just Enter)

        self.waiting_for_response = False

    def get_interactive_response(self, prompt_text, default_response=""):
        """Get user response to interactive prompt (thread-safe)"""
        self.interactive_response = None
        self.waiting_for_response = True
        self.interactive_prompt_signal.emit(prompt_text, default_response)

        # Wait for response with timeout
        max_wait = 300  # 30 seconds
        waited = 0
        while self.waiting_for_response and waited < max_wait:
            time.sleep(0.1)
            waited += 1

        return self.interactive_response or "\n"

    def _show_wine_version_dialog_safe(self):
        """Show professional Wine version selection dialog (called from main thread)"""
        dialog = QDialog()
        dialog.setWindowTitle("Choose Wine Version")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing - adapt to screen size and content
        # Get screen size to adjust sizes
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        # Calculate optimal sizes based on screen size
        # Account for 5 Wine version options now
        if screen_width < 800 or screen_height < 600:
            # Small screen - use smaller sizes
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(350, int(screen_height * 0.7))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(450, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            # Medium screen
            min_width = 500
            min_height = 400
            default_width = 650
            default_height = 550
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            # Large screen
            min_width = 550
            min_height = 450
            default_width = 700
            default_height = 600
            max_width = 900
            max_height = 800

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)

        # Make dialog resizable
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet
        if self.dark_mode:
            dialog_style = """
                QDialog {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 13px;
                    color: #b0b0b0;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.5;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton, QPushButton#installButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover, QPushButton#installButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed, QPushButton#installButton:pressed {
                    background-color: #3db9a0;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #2d2d2d;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #666666;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        else:
            dialog_style = """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 12px;
                    color: #666666;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#installButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#installButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#installButton:pressed {
                    background-color: #3d8b40;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """

        dialog.setStyleSheet(dialog_style)

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        # Responsive margins - smaller on small screens
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("Choose Wine Version")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Select which Wine version you would like to install. "
            "You can switch versions later by running 'Setup Wine Environment' again."
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        # Create button group to ensure only one radio button is selected at a time
        button_group = QButtonGroup(dialog)

        # Wine 11.0 option - clean frame with radio button and description (Recommended)
        wine_110_frame = QFrame()
        wine_110_frame.setObjectName("optionFrame")
        wine_110_layout = QVBoxLayout(wine_110_frame)
        wine_110_layout.setContentsMargins(12, 10, 12, 10)
        wine_110_layout.setSpacing(6)
        wine_110_radio = QRadioButton("Wine 11.0 (Recommended)")
        wine_110_radio.setChecked(True)
        wine_110_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        wine_110_layout.addWidget(wine_110_radio)
        wine_110_desc = QLabel(
            "ElementalWarrior Wine 11.0 with AMD GPU and OpenCL patches. Latest version with best compatibility and performance for most systems."
        )
        wine_110_desc.setObjectName("optionDescription")
        wine_110_desc.setWordWrap(True)
        wine_110_desc.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        wine_110_layout.addWidget(wine_110_desc)
        options_layout.addWidget(wine_110_frame)
        button_group.addButton(wine_110_radio, 0)

        # Wine 10.10 option - clean frame with radio button and description
        wine_1010_frame = QFrame()
        wine_1010_frame.setObjectName("optionFrame")
        wine_1010_layout = QVBoxLayout(wine_1010_frame)
        wine_1010_layout.setContentsMargins(12, 10, 12, 10)
        wine_1010_layout.setSpacing(6)
        wine_1010_radio = QRadioButton("Wine 10.10")
        wine_1010_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        wine_1010_layout.addWidget(wine_1010_radio)
        wine_1010_desc = QLabel(
            "ElementalWarrior Wine 10.10 with AMD GPU and OpenCL patches. Previous stable version."
        )
        wine_1010_desc.setObjectName("optionDescription")
        wine_1010_desc.setWordWrap(True)
        wine_1010_desc.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        wine_1010_layout.addWidget(wine_1010_desc)
        options_layout.addWidget(wine_1010_frame)
        button_group.addButton(wine_1010_radio, 1)

        # Wine 9.14 option - clean frame with radio button and description
        wine_914_frame = QFrame()
        wine_914_frame.setObjectName("optionFrame")
        wine_914_layout = QVBoxLayout(wine_914_frame)
        wine_914_layout.setContentsMargins(12, 10, 12, 10)
        wine_914_layout.setSpacing(6)
        wine_914_radio = QRadioButton("Wine 9.14 (Legacy)")
        wine_914_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        wine_914_layout.addWidget(wine_914_radio)
        wine_914_desc = QLabel(
            "Legacy version with AMD GPU and OpenCL patches. Fallback option if you encounter issues with newer versions."
        )
        wine_914_desc.setObjectName("optionDescription")
        wine_914_desc.setWordWrap(True)
        wine_914_desc.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        wine_914_layout.addWidget(wine_914_desc)
        options_layout.addWidget(wine_914_frame)
        button_group.addButton(wine_914_radio, 2)

        # Add scroll area to main layout with stretch factor
        main_layout.addWidget(scroll_area, 1)

        # Buttons - fixed at bottom, responsive sizing
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        # Get result
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            if wine_110_radio.isChecked():
                self.question_dialog_response = "Wine 11.0 (Recommended)"
            elif wine_1010_radio.isChecked():
                self.question_dialog_response = "Wine 10.10"
            elif wine_914_radio.isChecked():
                self.question_dialog_response = "Wine 9.14 (Legacy)"
        else:
            # User cancelled - return "Cancel" to match expected format
            self.question_dialog_response = "Cancel"

        self.waiting_for_question_response = False

    def _show_question_dialog_safe(self, title, message, buttons):
        """Show question dialog (called from main thread)"""
        # Check if this is a Wine version selection dialog
        is_wine_version_dialog = (
            "Wine Version" in title
            or "Wine version" in title
            or any("Wine 9.14" in btn or "Wine 10.10" in btn for btn in buttons)
        )
        if is_wine_version_dialog:
            self._show_wine_version_dialog_safe()
            return

        # Convert button list to QMessageBox buttons
        qbuttons = QMessageBox.StandardButton.NoButton
        for btn in buttons:
            if btn == "Yes":
                qbuttons |= QMessageBox.StandardButton.Yes
            elif btn == "No":
                qbuttons |= QMessageBox.StandardButton.No
            elif btn == "Retry":
                qbuttons |= QMessageBox.StandardButton.Retry
            elif btn == "Cancel":
                qbuttons |= QMessageBox.StandardButton.Cancel

        # Create message box and apply theme
        msg_box = QMessageBox()
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(qbuttons)
        msg_box.setStyleSheet(self.get_messagebox_stylesheet())
        reply = msg_box.exec()

        # Store response
        if reply == QMessageBox.StandardButton.Yes:
            self.question_dialog_response = "Yes"
        elif reply == QMessageBox.StandardButton.No:
            self.question_dialog_response = "No"
        elif reply == QMessageBox.StandardButton.Retry:
            self.question_dialog_response = "Retry"
        elif reply == QMessageBox.StandardButton.Cancel:
            self.question_dialog_response = "Cancel"
        else:
            self.question_dialog_response = "Cancel"

        self.waiting_for_question_response = False

    def show_question_dialog(self, title, message, buttons=["Yes", "No"]):
        """Show question dialog (thread-safe)"""
        self.question_dialog_response = None
        self.waiting_for_question_response = True
        self.question_dialog_signal.emit(title, message, buttons)

        # Wait for response indefinitely - let user take all the time they need
        # Only exit if operation is actually cancelled by user (via cancel button)
        while self.waiting_for_question_response:
            # Check if operation was cancelled by user (not timeout)
            if self.operation_cancelled:
                self.waiting_for_question_response = False
                return "Cancel"
            time.sleep(0.1)

        return self.question_dialog_response or "Cancel"

    def detect_cpu_generation(self):
        """Detect CPU generation using the V1-V5 method based on CPU model name.

        Returns:
            str: CPU generation ("V1", "V2", "V3", "V4", "V5", or "Unknown")
            bool: True if CPU is older (V1, V2, V3)
        """
        try:
            # Read CPU info from /proc/cpuinfo
            cpu_info = ""
            if Path("/proc/cpuinfo").exists():
                with open("/proc/cpuinfo", "r") as f:
                    cpu_info = f.read()

            # Try lscpu as fallback
            if not cpu_info or "model name" not in cpu_info.lower():
                try:
                    success, stdout, _ = self.run_command(
                        ["lscpu"], check=False, capture=True
                    )
                    if success:
                        cpu_info = stdout
                except Exception:
                    pass

            if not cpu_info:
                return "Unknown", False

            cpu_info_lower = cpu_info.lower()

            # AMD Detection (Zen architecture) - check in order from newest to oldest to avoid false matches
            # V5: Zen 4 (2022-2023) - Ryzen 7000 (desktop), Ryzen 7040 (mobile)
            if any(
                x in cpu_info_lower for x in ["ryzen 7", "ryzen 7000", "ryzen 7040"]
            ):
                return "V5", False

            # V4: Zen 3 (2020-2021) and Zen 5 (2024-2025) - Ryzen 5000, Ryzen 9000, Ryzen AI 300
            if any(
                x in cpu_info_lower
                for x in [
                    "ryzen 5",
                    "ryzen 5000",
                    "ryzen 9",
                    "ryzen 9000",
                    "ryzen ai 300",
                ]
            ):
                return "V4", False

            # V3: Zen 2 (2019-2020) - Ryzen 3000 (desktop), Ryzen 4000U/H (mobile)
            # Check for 4000 series first (mobile), then 3000 desktop (but not 3000U)
            if any(x in cpu_info_lower for x in ["ryzen 4", "ryzen 4000"]):
                return "V3", True
            if "ryzen 3" in cpu_info_lower or "ryzen 3000" in cpu_info_lower:
                # Check if it's not V2 (3000U is V2)
                if "3000u" not in cpu_info_lower and "pro 3700u" not in cpu_info_lower:
                    return "V3", True

            # V2: Zen+ (2018-2019) - Ryzen 2000 (desktop), Ryzen 3000U (mobile)
            if any(x in cpu_info_lower for x in ["ryzen 3000u", "ryzen 7 pro 3700u"]):
                return "V2", True
            if "ryzen 2" in cpu_info_lower or "ryzen 2000" in cpu_info_lower:
                # Check if it's not V1 (2000U is V1, 2000 desktop is V2)
                if "2000u" not in cpu_info_lower:
                    return "V2", True

            # V1: Zen (2017) - Ryzen 1000 (desktop), Ryzen 2000U (mobile)
            if any(
                x in cpu_info_lower for x in ["ryzen 1", "ryzen 1000", "ryzen 2000u"]
            ):
                return "V1", True

            # Intel Detection
            # V1: Broadwell (5th Gen, 2014-2015) - i7-5600U, i5-5300U
            if any(x in cpu_info_lower for x in ["i7-5600", "i5-5300", "broadwell"]):
                return "V1", True

            # V2: Skylake (6th Gen, 2015-2016) - i7-6600U, i5-6200U
            if any(x in cpu_info_lower for x in ["i7-6600", "i5-6200", "skylake"]):
                return "V2", True

            # V3: Kaby Lake (7th Gen, 2016-2017), Coffee Lake (8th Gen, 2017-2018)
            # i7-7600U, i7-8650U
            if any(
                x in cpu_info_lower
                for x in ["i7-7600", "i7-8650", "kaby lake", "coffee lake"]
            ):
                return "V3", True

            # V4: Ice Lake (10th Gen, 2019), Tiger Lake (11th Gen, 2020), Meteor Lake / Arrow Lake (14th Gen, 2024-2025)
            # i7-1065G7, i7-1165G7, i7-14700K
            if any(
                x in cpu_info_lower
                for x in [
                    "i7-1065",
                    "i7-1165",
                    "i7-14700",
                    "ice lake",
                    "tiger lake",
                    "meteor lake",
                    "arrow lake",
                ]
            ):
                return "V4", False

            # V5: Alder Lake (12th Gen, 2021), Raptor Lake (13th Gen, 2022-2023)
            # i7-12700K, i7-13700K
            if any(
                x in cpu_info_lower
                for x in ["i7-12700", "i7-13700", "alder lake", "raptor lake"]
            ):
                return "V5", False

            # Try to detect by generation number in model name
            # Intel: Look for patterns like "Core i7-5xxx", "Core i5-6xxx", etc.
            intel_gen_match = re.search(
                r"core\s+i[357]-([0-9])([0-9]{3})", cpu_info_lower
            )
            if intel_gen_match:
                gen_digit = int(intel_gen_match.group(1))
                if gen_digit == 5:
                    return "V1", True
                elif gen_digit == 6:
                    return "V2", True
                elif gen_digit == 7:
                    return "V3", True
                elif gen_digit in [10, 11, 14]:
                    return "V4", False
                elif gen_digit in [12, 13]:
                    return "V5", False

            # AMD: Look for Ryzen model numbers
            amd_match = re.search(r"ryzen\s+([0-9])([0-9]{3})", cpu_info_lower)
            if amd_match:
                first_digit = int(amd_match.group(1))
                if first_digit == 1:
                    return "V1", True
                elif first_digit == 2:
                    # Could be V1 (2000U) or V2 (2000 desktop) - default to V2
                    return "V2", True
                elif first_digit == 3:
                    # Could be V2 (3000U) or V3 (3000 desktop) - check for U suffix
                    if "u" in cpu_info_lower or "pro 3700u" in cpu_info_lower:
                        return "V2", True
                    return "V3", True
                elif first_digit == 4:
                    return "V3", True
                elif first_digit == 5:
                    return "V4", False
                elif first_digit == 7:
                    return "V5", False
                elif first_digit == 9:
                    return "V4", False

            return "Unknown", False
        except Exception as e:
            self.log(f"Error detecting CPU generation: {e}", "warning")
            return "Unknown", False

    def get_wine_dir(self):
        """Get the Wine directory path"""
        return Path(self.directory) / "ElementalWarriorWine"

    def get_wine_path(self, binary="wine"):
        """Get the path to a Wine binary"""
        return self.get_wine_dir() / "bin" / binary

    def get_current_wine_version(self):
        """Get the current ElementalWarrior Wine version (9.14, 10.10, or 11.0)"""
        # Try regular wine first
        wine = self.get_wine_path("wine")
        wine_staging = self.get_wine_path("wine-staging")

        # Check both wine and wine-staging binaries
        for wine_bin in [wine, wine_staging]:
            if wine_bin.exists():
                try:
                    success, stdout, _ = self.run_command(
                        [str(wine_bin), "--version"], check=False, capture=True
                    )
                    if success and stdout:
                        version_match = re.search(r"wine-(\d+\.\d+)", stdout)
                        if version_match:
                            version = version_match.group(1)
                            # Map actual Wine version to ElementalWarrior version
                            if version.startswith("9."):
                                return "9.14"
                            elif version.startswith("10."):
                                return "10.10"
                            elif version.startswith("11."):
                                return "11.0"
                except Exception:
                    continue
        return None

    def get_wine_tkg_for_installer(self, binary="wine"):
        """Get wine-tkg binary path for running installers, fallback to regular wine or wine-staging if not available"""
        wine_tkg_bin = self.get_wine_tkg_path(binary)
        if wine_tkg_bin and wine_tkg_bin.exists():
            return str(wine_tkg_bin)

        # Fallback to regular wine
        wine_bin = self.get_wine_path(binary)
        if wine_bin.exists():
            return str(wine_bin)

        # Final fallback to wine-staging
        wine_staging_bin = self.get_wine_path(f"{binary}-staging")
        if wine_staging_bin.exists():
            return str(wine_staging_bin)

        # Ultimate fallback
        return str(wine_bin)

    def get_wine_tkg_dir(self):
        """Get the wine-tkg directory path"""
        return Path(self.directory) / "wine-tkg"

    def get_wine_tkg_path(self, binary="wine"):
        """Get the path to a wine-tkg binary"""
        self.log(f"DEBUG: get_wine_tkg_path() called for binary: {binary}", "info")
        wine_tkg_dir = self.get_wine_tkg_dir()
        self.log(f"DEBUG: wine-tkg directory: {wine_tkg_dir}", "info")

        if not wine_tkg_dir.exists():
            self.log(
                f"DEBUG: wine-tkg directory does not exist: {wine_tkg_dir}", "info"
            )
            return None

        self.log(f"DEBUG: Checking for binary: {binary}", "info")

        # Check if binary exists directly in wine_tkg_dir/bin/ (direct extraction)
        direct_path = wine_tkg_dir / "bin" / binary
        self.log(f"DEBUG: Checking direct path: {direct_path}", "info")
        if direct_path.exists():
            self.log(f"DEBUG: ✓ Found binary at direct path: {direct_path}", "info")
            return direct_path
        else:
            self.log(f"DEBUG: ✗ Direct path does not exist", "info")

        # Check if it's in a subdirectory (like wine-10.19-staging-amd64/bin/wine)
        self.log(f"DEBUG: Checking subdirectories...", "info")
        try:
            subdirs = list(wine_tkg_dir.iterdir())
            self.log(f"DEBUG: Found {len(subdirs)} items in wine-tkg directory", "info")

            for subdir in subdirs:
                if subdir.is_dir():
                    self.log(f"DEBUG:   Checking subdirectory: {subdir.name}", "info")

                    # Check subdir/bin/binary
                    subdir_bin = subdir / "bin" / binary
                    self.log(f"DEBUG:     Checking: {subdir_bin}", "info")
                    if subdir_bin.exists():
                        self.log(f"DEBUG: ✓ Found binary at: {subdir_bin}", "info")
                        return subdir_bin

                    # Also check if bin is directly in subdir (some archives might have different structure)
                    subdir_direct = subdir / binary
                    self.log(f"DEBUG:     Checking direct: {subdir_direct}", "info")
                    if subdir_direct.exists():
                        self.log(f"DEBUG: ✓ Found binary at: {subdir_direct}", "info")
                        return subdir_direct
        except Exception as e:
            self.log(f"DEBUG: Error iterating subdirectories: {e}", "warning")

        # Last resort: recursive search for the binary (but limit depth to avoid performance issues)
        self.log(f"DEBUG: Performing recursive search for '{binary}'...", "info")
        try:
            found_paths = []
            for path in wine_tkg_dir.rglob(binary):
                if path.is_file() and path.name == binary:
                    found_paths.append(path)
                    # Make sure it's executable or at least looks like a binary
                    try:
                        is_executable = path.stat().st_mode & 0o111
                        has_no_suffix = path.suffix == ""
                        if is_executable or has_no_suffix:
                            self.log(
                                f"DEBUG: ✓ Found binary via recursive search: {path}",
                                "info",
                            )
                            return path
                        else:
                            self.log(
                                f"DEBUG:   Found '{binary}' but not executable: {path}",
                                "info",
                            )
                    except Exception as e:
                        self.log(f"DEBUG:   Error checking file {path}: {e}", "warning")

            if found_paths:
                self.log(
                    f"DEBUG: Found {len(found_paths)} files named '{binary}' but none are valid binaries",
                    "info",
                )
                for p in found_paths[:5]:
                    self.log(f"DEBUG:   - {p}", "info")
        except Exception as e:
            self.log(f"DEBUG: Error during recursive search: {e}", "warning")

        self.log(f"DEBUG: ✗ Binary '{binary}' not found in wine-tkg directory", "info")
        return None

    def _debug_log(self, message, level="info"):
        """Debug logging helper - prints to stderr (unbuffered) AND logs to UI/file AND debug file"""
        # Use stderr which is unbuffered and more reliable for GUI apps
        sys.stderr.write(f"[DEBUG] {message}\n")
        sys.stderr.flush()  # Force immediate output

        # Also write to a debug log file
        debug_log_path = Path.home() / "wine-tkg-debug.log"
        try:
            with open(debug_log_path, "a", encoding="utf-8") as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {message}\n")
                f.flush()
        except Exception:
            pass  # Don't fail if we can't write to debug file

        self.log(f"DEBUG: {message}", level)

    def ensure_wine_tkg(self):
        """Download and extract wine-tkg if not already present"""
        # Print to stderr as backup (visible in terminal, unbuffered)
        sys.stderr.write("\n" + "=" * 80 + "\n")
        sys.stderr.write("DEBUG: Starting wine-tkg setup process\n")
        sys.stderr.write("=" * 80 + "\n")
        sys.stderr.flush()

        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )
        self.log("DEBUG: Starting wine-tkg setup process", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )

        # Step 1: Get directory paths
        self._debug_log("Step 1 - Getting directory paths")
        wine_tkg_dir = self.get_wine_tkg_dir()
        self._debug_log(f"wine-tkg directory: {wine_tkg_dir}")
        self._debug_log(f"wine-tkg directory exists: {wine_tkg_dir.exists()}")

        # Step 2: Check if already extracted
        self._debug_log("Step 2 - Checking if wine-tkg is already available")
        wine_tkg_bin = self.get_wine_tkg_path("wine")
        self._debug_log(f"wine-tkg binary path: {wine_tkg_bin}")

        if wine_tkg_bin:
            exists = wine_tkg_bin.exists()
            self._debug_log(f"wine-tkg binary exists check: {exists}")
            if exists:
                self._debug_log(
                    f"✓ wine-tkg is already available at: {wine_tkg_bin}", "success"
                )
                return True
            else:
                self._debug_log(
                    f"✗ wine-tkg path exists but file not found: {wine_tkg_bin}",
                    "warning",
                )
        else:
            self._debug_log("wine-tkg binary not found, will download and extract")

        # Step 3: Setup download parameters — fetch latest release from GitHub
        self.log("DEBUG: Step 3 - Setting up download parameters", "info")
        self.log("Fetching latest wine-tkg version from GitHub...", "info")
        wine_tkg_version = None
        try:
            api_url = "https://api.github.com/repos/Kron4ek/Wine-Builds/releases/latest"
            req = urllib.request.Request(api_url)
            req.add_header("User-Agent", "AffinityLinuxInstaller")
            with urllib.request.urlopen(req, timeout=15) as resp:
                release_data = json.loads(resp.read().decode())
            wine_tkg_version = release_data.get("tag_name", "").lstrip("v")
            if wine_tkg_version:
                self.log(f"Latest wine-tkg version: {wine_tkg_version}", "info")
            else:
                self.log(
                    "Could not parse version from GitHub API, falling back to 11.0",
                    "warning",
                )
                wine_tkg_version = "11.0"
        except Exception as e:
            self.log(
                f"Failed to fetch latest wine-tkg version: {e} — falling back to 11.0",
                "warning",
            )
            wine_tkg_version = "11.0"

        wine_tkg_filename = f"wine-{wine_tkg_version}-staging-tkg-amd64-wow64.tar.xz"
        wine_tkg_url = f"https://github.com/Kron4ek/Wine-Builds/releases/download/{wine_tkg_version}/{wine_tkg_filename}"
        wine_tkg_file = wine_tkg_dir / wine_tkg_filename
        self.log(f"DEBUG: Download URL: {wine_tkg_url}", "info")
        self.log(f"DEBUG: Target file: {wine_tkg_file}", "info")

        # Step 4: Create directory
        self.log("DEBUG: Step 4 - Creating wine-tkg directory", "info")
        try:
            wine_tkg_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"DEBUG: ✓ Directory created/verified: {wine_tkg_dir}", "info")
            self.log(
                f"DEBUG: Directory exists after creation: {wine_tkg_dir.exists()}",
                "info",
            )
        except Exception as e:
            error_msg = f"Failed to create wine-tkg directory: {e}"
            sys.stderr.write(f"ERROR: {error_msg}\n")
            sys.stderr.write(f"Error type: {type(e).__name__}\n")
            import traceback

            sys.stderr.write(f"Traceback:\n{traceback.format_exc()}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Error type: {type(e).__name__}", "error")
            self.log(f"DEBUG: Traceback:\n{traceback.format_exc()}", "error")
            return False

        # Step 5: Check if file already exists
        self.log("DEBUG: Step 5 - Checking if archive file already exists", "info")
        if wine_tkg_file.exists():
            file_size = wine_tkg_file.stat().st_size
            self.log(
                f"DEBUG: Archive file already exists, size: {file_size} bytes", "info"
            )
            if file_size == 0:
                self.log("DEBUG: Archive file is empty, will re-download", "warning")
                try:
                    wine_tkg_file.unlink()
                    self.log("DEBUG: ✓ Empty file removed", "info")
                except Exception as e:
                    self.log(f"DEBUG: ✗ Failed to remove empty file: {e}", "error")
            else:
                self.log(
                    "DEBUG: Archive file exists and has content, will use it", "info"
                )
        else:
            self.log("DEBUG: Archive file does not exist, will download", "info")

        # Step 6: Download wine-tkg
        self.log("DEBUG: Step 6 - Downloading wine-tkg archive", "info")
        self.log("Downloading wine-tkg...", "info")
        sys.stderr.write(f"\n[WINE-TKG] Starting download from: {wine_tkg_url}\n")
        sys.stderr.write(f"[WINE-TKG] Saving to: {wine_tkg_file}\n")
        sys.stderr.flush()
        try:
            download_result = self.download_file(
                wine_tkg_url, str(wine_tkg_file), "wine-tkg"
            )
            sys.stderr.write(f"[WINE-TKG] Download result: {download_result}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: Download result: {download_result}", "info")
        except Exception as e:
            error_msg = f"Exception during download: {e}"
            sys.stderr.write(f"[WINE-TKG] ERROR: {error_msg}\n")
            import traceback

            sys.stderr.write(f"[WINE-TKG] Traceback:\n{traceback.format_exc()}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            download_result = False

        if not download_result:
            error_msg = "Failed to download wine-tkg archive"
            sys.stderr.write(f"\nERROR: {error_msg}\n")
            sys.stderr.write("Possible causes:\n")
            sys.stderr.write(f"  - Network connectivity issues\n")
            sys.stderr.write(f"  - URL may be invalid or changed: {wine_tkg_url}\n")
            sys.stderr.write(f"  - Insufficient disk space\n")
            sys.stderr.write(
                f"  - Permission denied writing to: {wine_tkg_file.parent}\n"
            )
            if wine_tkg_file.exists():
                file_size = wine_tkg_file.stat().st_size
                sys.stderr.write(
                    f"  - Partial file exists with size: {file_size} bytes\n"
                )
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Possible causes:", "error")
            self.log(f"DEBUG:   - Network connectivity issues", "error")
            self.log(
                f"DEBUG:   - URL may be invalid or changed: {wine_tkg_url}", "error"
            )
            self.log(f"DEBUG:   - Insufficient disk space", "error")
            self.log(
                f"DEBUG:   - Permission denied writing to: {wine_tkg_file.parent}",
                "error",
            )
            if wine_tkg_file.exists():
                file_size = wine_tkg_file.stat().st_size
                self.log(
                    f"DEBUG:   - Partial file exists with size: {file_size} bytes",
                    "error",
                )
            return False

        # Verify download
        if wine_tkg_file.exists():
            file_size = wine_tkg_file.stat().st_size
            self.log(
                f"DEBUG: ✓ Download completed, file size: {file_size} bytes", "info"
            )
            if file_size == 0:
                error_msg = "Downloaded file is empty"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: Download completed but file has 0 bytes", "error"
                )
                return False
        else:
            error_msg = "Download reported success but file not found"
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Cause: File should exist at: {wine_tkg_file}", "error")
            return False

        if self.check_cancelled():
            self.log("DEBUG: Operation cancelled by user", "warning")
            return False

        # Step 7: Extract wine-tkg
        self.log("DEBUG: Step 7 - Extracting wine-tkg archive", "info")
        self.update_progress_text("Extracting wine-tkg...")
        self.log("Extracting wine-tkg...", "info")

        extraction_success = False
        extraction_method = None

        # Try Python lzma module first
        self.log(
            "DEBUG: Step 7a - Attempting extraction with Python lzma module", "info"
        )
        try:
            import lzma

            self.log("DEBUG: ✓ lzma module available", "info")

            try:
                self.log("DEBUG: Opening xz file with lzma...", "info")
                with lzma.open(wine_tkg_file, "rb") as xz_file:
                    self.log("DEBUG: ✓ xz file opened successfully", "info")

                    self.log("DEBUG: Opening tar archive...", "info")
                    with tarfile.open(fileobj=xz_file, mode="r") as tar:
                        self.log("DEBUG: ✓ tar archive opened successfully", "info")

                        # Check archive structure
                        self.log("DEBUG: Analyzing archive structure...", "info")
                        members = tar.getmembers()
                        self.log(
                            f"DEBUG: Archive contains {len(members)} entries", "info"
                        )
                        if members:
                            first_member = members[0].name
                            self.log(f"DEBUG: First entry: '{first_member}'", "info")
                            # Show first few entries
                            for i, member in enumerate(members[:5]):
                                self.log(
                                    f"DEBUG:   Entry {i + 1}: {member.name} ({member.size} bytes)",
                                    "info",
                                )

                        # Try with filter='data' first (Python 3.12+)
                        self.log(
                            "DEBUG: Attempting extraction with filter='data' (Python 3.12+)...",
                            "info",
                        )
                        try:
                            tar.extractall(wine_tkg_dir, filter="data")
                            extraction_success = True
                            extraction_method = "Python lzma with filter='data'"
                            self.log(
                                "DEBUG: ✓ Extraction successful with filter='data'",
                                "info",
                            )
                        except TypeError as e:
                            self.log(f"DEBUG: filter='data' not supported: {e}", "info")
                            self.log(
                                "DEBUG: Attempting extraction without filter (older Python)...",
                                "info",
                            )
                            tar.extractall(wine_tkg_dir)
                            extraction_success = True
                            extraction_method = "Python lzma without filter"
                            self.log(
                                "DEBUG: ✓ Extraction successful without filter", "info"
                            )
            except Exception as e:
                error_msg = f"Error during extraction with lzma: {e}"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Error type: {type(e).__name__}", "error")
                import traceback

                self.log(f"DEBUG: Traceback:\n{traceback.format_exc()}", "error")

        except ImportError:
            self.log("DEBUG: ✗ lzma module not available, will use xz command", "info")
            extraction_method = None

        # Fallback to xz command if lzma module not available or extraction failed
        if not extraction_success:
            self.log("DEBUG: Step 7b - Attempting extraction with xz command", "info")

            # Check for xz command
            xz_available = self.check_command("xz")
            unxz_available = self.check_command("unxz")
            self.log(f"DEBUG: xz command available: {xz_available}", "info")
            self.log(f"DEBUG: unxz command available: {unxz_available}", "info")

            if not xz_available and not unxz_available:
                error_msg = "Neither xz nor unxz command is available"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: Required for extracting .tar.xz files when Python lzma module is unavailable",
                    "error",
                )
                self.log(
                    f"DEBUG: Solution: Install xz package (e.g., 'sudo pacman -S xz' or 'sudo apt install xz-utils')",
                    "error",
                )
                return False

            xz_cmd = "xz" if xz_available else "unxz"
            self.log(f"DEBUG: Using command: {xz_cmd}", "info")

            # Decompress with xz
            tar_file = wine_tkg_file.with_suffix(".tar")
            self.log(f"DEBUG: Decompressing to: {tar_file}", "info")

            success, stdout, stderr = self.run_command(
                [xz_cmd, "-d", "-k", str(wine_tkg_file)], check=True
            )
            self.log(f"DEBUG: Decompression result: success={success}", "info")
            if stdout:
                self.log(f"DEBUG: Decompression stdout: {stdout[:200]}", "info")
            if stderr:
                self.log(f"DEBUG: Decompression stderr: {stderr[:200]}", "info")

            if not success:
                error_msg = "Failed to decompress wine-tkg archive with xz"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: xz command failed to decompress the archive",
                    "error",
                )
                if stderr:
                    self.log(f"DEBUG: Error output: {stderr}", "error")
                return False

            if not tar_file.exists():
                error_msg = "Decompression reported success but tar file not found"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Cause: Expected tar file at: {tar_file}", "error")
                return False

            tar_size = tar_file.stat().st_size
            self.log(
                f"DEBUG: ✓ Decompression successful, tar file size: {tar_size} bytes",
                "info",
            )

            # Extract tar file
            self.log("DEBUG: Extracting tar archive...", "info")
            try:
                with tarfile.open(tar_file, "r") as tar:
                    self.log("DEBUG: ✓ tar file opened successfully", "info")

                    members = tar.getmembers()
                    self.log(f"DEBUG: Archive contains {len(members)} entries", "info")

                    try:
                        tar.extractall(wine_tkg_dir, filter="data")
                        extraction_success = True
                        extraction_method = "xz command + tar with filter='data'"
                        self.log(
                            "DEBUG: ✓ Extraction successful with filter='data'", "info"
                        )
                    except TypeError:
                        tar.extractall(wine_tkg_dir)
                        extraction_success = True
                        extraction_method = "xz command + tar without filter"
                        self.log(
                            "DEBUG: ✓ Extraction successful without filter", "info"
                        )
            except Exception as e:
                error_msg = f"Error extracting tar file: {e}"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Error type: {type(e).__name__}", "error")
                import traceback

                self.log(f"DEBUG: Traceback:\n{traceback.format_exc()}", "error")
                return False

            # Clean up intermediate tar file
            if tar_file.exists():
                try:
                    tar_file.unlink()
                    self.log("DEBUG: ✓ Intermediate tar file cleaned up", "info")
                except Exception as e:
                    self.log(
                        f"DEBUG: Warning: Failed to clean up tar file: {e}", "warning"
                    )

        if not extraction_success:
            error_msg = "Extraction did not complete successfully"
            sys.stderr.write(f"\nERROR: {error_msg}\n")
            sys.stderr.write("Cause: All extraction methods failed\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Cause: All extraction methods failed", "error")
            return False

        self.log(
            f"DEBUG: ✓ Extraction completed using method: {extraction_method}", "info"
        )

        # Step 8: Clean up archive file
        self.log("DEBUG: Step 8 - Cleaning up archive file", "info")
        if wine_tkg_file.exists():
            try:
                wine_tkg_file.unlink()
                self.log("DEBUG: ✓ Archive file cleaned up", "info")
            except Exception as e:
                self.log(
                    f"DEBUG: Warning: Failed to clean up archive file: {e}", "warning"
                )

        # Step 9: Verify extraction
        self.log("DEBUG: Step 9 - Verifying extraction", "info")
        self.log(f"DEBUG: Checking extraction directory: {wine_tkg_dir}", "info")

        if not wine_tkg_dir.exists():
            error_msg = "Extraction directory does not exist after extraction"
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(
                f"DEBUG: Cause: Directory was removed or never created: {wine_tkg_dir}",
                "error",
            )
            return False

        # List extracted contents
        try:
            contents = list(wine_tkg_dir.iterdir())
            self.log(
                f"DEBUG: Extracted directory contains {len(contents)} items", "info"
            )
            for i, item in enumerate(contents[:10]):  # Show first 10 items
                item_type = "directory" if item.is_dir() else "file"
                size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
                self.log(
                    f"DEBUG:   Item {i + 1}: {item.name} ({item_type}){size}", "info"
                )
            if len(contents) > 10:
                self.log(f"DEBUG:   ... and {len(contents) - 10} more items", "info")
        except Exception as e:
            self.log(
                f"DEBUG: Warning: Failed to list directory contents: {e}", "warning"
            )

        # Step 10: Find wine binary
        self.log("DEBUG: Step 10 - Searching for wine binary", "info")
        wine_tkg_bin = self.get_wine_tkg_path("wine")
        self.log(f"DEBUG: get_wine_tkg_path() returned: {wine_tkg_bin}", "info")

        if wine_tkg_bin:
            if wine_tkg_bin.exists():
                self.log(f"DEBUG: ✓ wine binary found at: {wine_tkg_bin}", "success")
                # Verify it's executable
                try:
                    is_executable = wine_tkg_bin.stat().st_mode & 0o111
                    self.log(
                        f"DEBUG: Binary is executable: {bool(is_executable)}", "info"
                    )
                    if not is_executable:
                        self.log(
                            "DEBUG: Warning: Binary is not executable, attempting to make it executable...",
                            "warning",
                        )
                        try:
                            wine_tkg_bin.chmod(0o755)
                            self.log("DEBUG: ✓ Made binary executable", "info")
                        except Exception as e:
                            self.log(
                                f"DEBUG: Warning: Failed to make executable: {e}",
                                "warning",
                            )
                except Exception as e:
                    self.log(
                        f"DEBUG: Warning: Could not check executable bit: {e}",
                        "warning",
                    )

                self.log(
                    f"wine-tkg extracted successfully at: {wine_tkg_bin}", "success"
                )
                return True
            else:
                error_msg = (
                    f"wine binary path exists but file not found: {wine_tkg_bin}"
                )
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: Path was returned but file does not exist", "error"
                )
        else:
            error_msg = "wine binary not found after extraction"
            sys.stderr.write(f"\nERROR: {error_msg}\n")
            sys.stderr.write("Cause: get_wine_tkg_path() returned None\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Cause: get_wine_tkg_path() returned None", "error")

        # Detailed search for debugging
        sys.stderr.write("\nPerforming detailed search for wine binary...\n")
        sys.stderr.write(f"Expected locations:\n")
        sys.stderr.write(f"  1. {wine_tkg_dir / 'bin' / 'wine'}\n")
        sys.stderr.write(f"  2. {wine_tkg_dir}/*/bin/wine (subdirectory)\n")
        sys.stderr.flush()
        self.log("DEBUG: Performing detailed search for wine binary...", "info")
        self.log(f"DEBUG: Expected locations:", "info")
        self.log(f"DEBUG:   1. {wine_tkg_dir / 'bin' / 'wine'}", "info")
        self.log(f"DEBUG:   2. {wine_tkg_dir}/*/bin/wine (subdirectory)", "info")

        # Search for any wine-related files
        wine_files_found = []
        try:
            for item in wine_tkg_dir.rglob("*"):
                if item.is_file() and "wine" in item.name.lower():
                    wine_files_found.append(item)
                    if len(wine_files_found) <= 10:
                        sys.stderr.write(
                            f"  Found wine-related file: {item.relative_to(wine_tkg_dir)}\n"
                        )
                        self.log(
                            f"DEBUG:   Found wine-related file: {item.relative_to(wine_tkg_dir)}",
                            "info",
                        )
        except Exception as e:
            sys.stderr.write(f"Warning: Error during recursive search: {e}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: Warning: Error during recursive search: {e}", "warning")

        if wine_files_found:
            sys.stderr.write(
                f"Found {len(wine_files_found)} wine-related files total\n"
            )
            sys.stderr.write("Most likely candidates:\n")
            self.log(
                f"DEBUG: Found {len(wine_files_found)} wine-related files total", "info"
            )
            self.log(f"DEBUG: Most likely candidates:", "info")
            for candidate in wine_files_found[:5]:
                if candidate.name == "wine" or candidate.name.startswith("wine"):
                    sys.stderr.write(f"  - {candidate}\n")
                    self.log(f"DEBUG:   - {candidate}", "info")
        else:
            sys.stderr.write("No wine-related files found in extraction directory\n")
            self.log(
                "DEBUG: No wine-related files found in extraction directory", "error"
            )

        sys.stderr.write(
            "\nERROR: wine-tkg extraction completed but binary not found\n"
        )
        sys.stderr.flush()
        self.log("DEBUG: ✗ wine-tkg extraction completed but binary not found", "error")
        return False

    def get_winetricks_env_with_tkg(self, base_env=None):
        """Get environment for winetricks with wine-tkg in PATH"""
        self.log("DEBUG: get_winetricks_env_with_tkg() called", "info")

        if base_env is None:
            env = os.environ.copy()
            self.log("DEBUG: Created new environment from os.environ", "info")
        else:
            env = base_env.copy()
            self.log("DEBUG: Created environment copy from base_env", "info")

        self.log("DEBUG: Searching for wine-tkg binary...", "info")
        wine_tkg_bin = self.get_wine_tkg_path("wine")
        self.log(f"DEBUG: get_wine_tkg_path() returned: {wine_tkg_bin}", "info")

        if wine_tkg_bin:
            self.log(f"DEBUG: wine-tkg binary path: {wine_tkg_bin}", "info")
            self.log(f"DEBUG: wine-tkg binary exists: {wine_tkg_bin.exists()}", "info")

            if wine_tkg_bin.exists():
                # Add wine-tkg bin directory to PATH so winetricks uses it
                wine_tkg_bin_dir = wine_tkg_bin.parent
                current_path = env.get("PATH", "")
                env["PATH"] = f"{wine_tkg_bin_dir}:{current_path}"
                self.log(f"DEBUG: ✓ Using wine-tkg from: {wine_tkg_bin_dir}", "info")
                self.log(
                    f"DEBUG: Updated PATH (first 200 chars): {env['PATH'][:200]}",
                    "info",
                )
                self.log(f"Using wine-tkg from: {wine_tkg_bin_dir}", "info")
            else:
                error_msg = "wine-tkg binary path returned but file does not exist"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Path was: {wine_tkg_bin}", "error")
                self.log("wine-tkg not found, using system wine", "warning")
        else:
            self.log("DEBUG: ✗ wine-tkg binary not found", "info")
            self.log("wine-tkg not found, using system wine", "warning")

        # ── Speed optimisations ───────────────────────────────────────────────
        # Suppress Wine debug output - major speedup per wineserver invocation
        env.setdefault("WINEDEBUG", "-all,fixme-all")

        # Use aria2c for multi-connection downloads if available, else curl, else wget
        if self.check_command("aria2c"):
            env["WINETRICKS_DOWNLOADER"] = "aria2c"
            self.log("winetricks: using aria2c for fast downloads", "info")
        elif self.check_command("curl"):
            env["WINETRICKS_DOWNLOADER"] = "curl"
        else:
            env["WINETRICKS_DOWNLOADER"] = "wget"

        # Disable winetricks GUI (ensures non-interactive even if DISPLAY is set)
        env["WINETRICKS_GUI"] = "none"

        # Keep wineserver alive between winetricks calls to avoid repeated cold starts
        env["WINESERVER_TIMEOUT"] = "60"
        return env

    def _register_process(self, proc):
        """Track a running subprocess for potential cancellation."""
        try:
            with self._process_lock:
                self._active_processes.add(proc)
        except Exception:
            pass

    def _unregister_process(self, proc):
        """Stop tracking a subprocess."""
        try:
            with self._process_lock:
                self._active_processes.discard(proc)
        except Exception:
            pass

    def _terminate_process(self, proc):
        """Terminate a subprocess and its process group safely."""
        try:
            # Try to terminate the whole process group first
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
            # Wait briefly, then force kill if still alive
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        finally:
            self._unregister_process(proc)

    def terminate_active_processes(self):
        """Terminate all active subprocesses started by this installer."""
        try:
            with self._process_lock:
                procs = list(self._active_processes)
            for p in procs:
                self._terminate_process(p)
        except Exception:
            pass

    def run_command(self, command, check=True, shell=False, capture=True, env=None):
        """Execute shell command with GUI sudo password support and cancellation."""
        try:
            # Convert command to list if it's a string
            if isinstance(command, str) and not shell:
                command = command.split()
            # Ensure command is a list
            if not isinstance(command, list):
                command = list(command)

            # Set up environment for non-interactive operation
            if env is None:
                env = os.environ.copy()

            # Force non-interactive mode for various tools
            env["DEBIAN_FRONTEND"] = "noninteractive"
            env["NEEDRESTART_MODE"] = "a"  # Auto-restart services without asking
            env["DEBIAN_PRIORITY"] = "critical"
            env["APT_LISTCHANGES_FRONTEND"] = "none"
            env["LANG"] = "C"  # Use C locale to avoid encoding issues
            env["LC_ALL"] = "C"

            # Check if this is a sudo command
            is_sudo = (
                isinstance(command, list) and len(command) > 0 and command[0] == "sudo"
            )

            # Unset SUDO_ASKPASS to force sudo to read password from stdin via -S flag
            # This prevents errors when askpass programs (like ksshaskpass) don't exist
            if is_sudo:
                env.pop("SUDO_ASKPASS", None)  # Remove SUDO_ASKPASS if it exists

            if is_sudo:
                # Get password if needed
                max_attempts = 3
                for attempt in range(max_attempts):
                    if self.cancel_event.is_set():
                        return False, "", "Cancelled"
                    password = self.get_sudo_password()
                    if password is None:
                        self.log("Authentication cancelled by user", "warning")
                        return False, "", "Authentication cancelled"
                    # Validate password first
                    if not self.sudo_password_validated:
                        if self.validate_sudo_password(password):
                            self.log("Authentication successful", "success")
                            break
                        else:
                            self.log(
                                "Authentication failed. Please try again.", "error"
                            )
                            self.sudo_password = None
                            self.sudo_password_validated = False
                            if attempt == max_attempts - 1:
                                return (
                                    False,
                                    "",
                                    "Authentication failed after multiple attempts",
                                )
                    else:
                        break

                # Run command with password via stdin
                # Add -S flag to read password from stdin if not present
                # Make sure -S is right after "sudo"
                # Create a copy to avoid modifying the original
                command = list(command)
                if len(command) > 1:
                    # Only add -S if it's not already in position 1 (right after sudo)
                    # Don't remove -S that's part of the actual command (like pacman -S)
                    if command[1] != "-S":
                        # Insert -S right after "sudo"
                        command.insert(1, "-S")
                else:
                    # Only "sudo" in command, add -S
                    command.append("-S")

                proc = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE if capture else None,
                    stderr=subprocess.PIPE if capture else None,
                    text=True,
                    env=env,  # Use the modified env that has SUDO_ASKPASS removed
                    preexec_fn=os.setsid,
                )
                self._register_process(proc)
                try:
                    # Send password to sudo via stdin using communicate() which handles stdin properly
                    password_input = f"{self.sudo_password}\n"

                    if capture:
                        stdout_acc = ""
                        stderr_acc = ""
                        # Read output without timeout for long-running commands like package installation
                        try:
                            # Use communicate with input - this is the safest way
                            out, err = proc.communicate(
                                input=password_input, timeout=None
                            )
                            stdout_acc += out or ""
                            stderr_acc += err or ""
                        except subprocess.TimeoutExpired:
                            # This shouldn't happen with timeout=None, but handle it just in case
                            if self.cancel_event.is_set():
                                self._terminate_process(proc)
                                return False, stdout_acc, "Cancelled"
                            # Force read remaining output
                            try:
                                out, err = proc.communicate()
                                stdout_acc += out or ""
                                stderr_acc += err or ""
                            except Exception:
                                pass
                        except Exception as e:
                            # Catch all exceptions including "I/O operation on closed file"
                            error_msg = str(e)
                            error_type = type(e).__name__

                            # Check if process completed successfully despite the error
                            try:
                                if proc.poll() is None:
                                    # Process still running, wait a bit
                                    proc.wait(timeout=2)
                            except Exception:
                                pass

                            # If return code is 0, the operation succeeded despite the exception
                            if proc.returncode == 0:
                                # Try to read any remaining output
                                try:
                                    if proc.stdout and not proc.stdout.closed:
                                        remaining = proc.stdout.read()
                                        if remaining:
                                            stdout_acc += remaining
                                except Exception:
                                    pass
                                try:
                                    if proc.stderr and not proc.stderr.closed:
                                        remaining = proc.stderr.read()
                                        if remaining:
                                            stderr_acc += remaining
                                except Exception:
                                    pass
                                # Operation succeeded, return success
                                return True, stdout_acc, stderr_acc

                            # Only report error if return code indicates failure
                            if (
                                "closed file" in error_msg.lower()
                                or "I/O operation" in error_msg
                            ):
                                # This is often a harmless error if the process succeeded
                                if proc.returncode == 0:
                                    return True, stdout_acc, stderr_acc
                                # If it failed, log it
                                self.log(
                                    f"Error during command execution ({error_type}): {error_msg}",
                                    "error",
                                )
                            else:
                                self.log(
                                    f"Error during command execution ({error_type}): {error_msg}",
                                    "error",
                                )

                            self._terminate_process(proc)
                            return False, stdout_acc, stderr_acc or error_msg

                        success = proc.returncode == 0
                        return success, stdout_acc, stderr_acc
                    else:
                        # No capture: send password and wait for completion
                        try:
                            proc.communicate(input=password_input, timeout=None)
                        except Exception as e:
                            # Catch all exceptions including "I/O operation on closed file"
                            error_msg = str(e)

                            # Check if process completed successfully despite the error
                            try:
                                if proc.poll() is None:
                                    proc.wait(timeout=2)
                            except Exception:
                                pass

                            # If return code is 0, operation succeeded despite the exception
                            if proc.returncode == 0:
                                return True, "", ""

                            # Only report error if return code indicates failure
                            if (
                                "closed file" in error_msg.lower()
                                or "I/O operation" in error_msg
                            ):
                                # This is often a harmless error if the process succeeded
                                if proc.returncode == 0:
                                    return True, "", ""
                                # If it failed, log it
                                self.log(
                                    f"Error during command execution: {error_msg}",
                                    "error",
                                )
                            else:
                                self.log(
                                    f"Error during command execution: {error_msg}",
                                    "error",
                                )

                            self._terminate_process(proc)
                            return False, "", error_msg
                        except subprocess.TimeoutExpired:
                            # This shouldn't happen with timeout=None, but handle it just in case
                            if self.cancel_event.is_set():
                                self._terminate_process(proc)
                                return False, "", "Cancelled"
                            try:
                                proc.communicate()
                            except Exception:
                                pass
                        return proc.returncode == 0, "", ""
                finally:
                    self._unregister_process(proc)
            else:
                # Non-sudo command, run normally with cancellation support
                proc = subprocess.Popen(
                    command
                    if not shell
                    else (command if isinstance(command, str) else " ".join(command)),
                    shell=shell,
                    stdout=subprocess.PIPE if capture else None,
                    stderr=subprocess.PIPE if capture else None,
                    text=capture,
                    env=env if env else os.environ.copy(),
                    preexec_fn=os.setsid,
                )
                self._register_process(proc)
                try:
                    if capture:
                        stdout_acc = ""
                        stderr_acc = ""
                        while True:
                            try:
                                out, err = proc.communicate(timeout=0.1)
                                stdout_acc += out or ""
                                stderr_acc += err or ""
                                break
                            except subprocess.TimeoutExpired:
                                if self.cancel_event.is_set():
                                    self._terminate_process(proc)
                                    return False, stdout_acc, "Cancelled"
                                continue
                        success = proc.returncode == 0
                        return success, stdout_acc, stderr_acc
                    else:
                        while True:
                            if self.cancel_event.is_set():
                                self._terminate_process(proc)
                                return False, "", "Cancelled"
                            if proc.poll() is not None:
                                break
                            time.sleep(0.1)
                        return proc.returncode == 0, "", ""
                finally:
                    self._unregister_process(proc)
        except Exception as e:
            return False, "", str(e)

    def run_command_streaming(self, command, env=None, progress_callback=None):
        """Execute command and stream output to log in real-time, cancellable.
        Also stores the full streamed text in self._last_stream_output_text for post-run heuristics."""
        self._last_stream_output_text = ""
        try:
            if isinstance(command, str):
                command = command.split()

            # Set up environment for non-interactive operation
            if env is None:
                env = os.environ.copy()

            # Force non-interactive mode for various tools
            env["DEBIAN_FRONTEND"] = "noninteractive"
            env["NEEDRESTART_MODE"] = "a"  # Auto-restart services without asking
            env["DEBIAN_PRIORITY"] = "critical"
            env["APT_LISTCHANGES_FRONTEND"] = "none"
            env["LANG"] = "C"  # Use C locale to avoid encoding issues
            env["LC_ALL"] = "C"

            # Unset SUDO_ASKPASS if this is a sudo command
            is_sudo = (
                isinstance(command, list) and len(command) > 0 and command[0] == "sudo"
            )
            if is_sudo:
                env.pop("SUDO_ASKPASS", None)

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                preexec_fn=os.setsid,
            )
            self._register_process(process)

            # Stream output line by line
            buffer = []
            for line in iter(process.stdout.readline, ""):
                if self.cancel_event.is_set():
                    self._terminate_process(process)
                    self._last_stream_output_text = "".join(buffer)
                    return False
                if line:
                    # Clean up the line and log it
                    line = line.rstrip()
                    if line:
                        buffer.append(line + "\n")
                        # Show important progress messages
                        line_lower = line.lower()
                        # Always show progress-related messages
                        if any(
                            keyword in line_lower
                            for keyword in [
                                "progress",
                                "downloading",
                                "installing",
                                "extracting",
                                "configuring",
                                "executing",
                                "running",
                                "done",
                                "complete",
                                "success",
                                "error",
                                "failed",
                                "warning",
                                "%",
                                "mb",
                                "kb",
                            ]
                        ):
                            self.log(f"  {line}", "info")

                            # Try to extract progress percentage if callback provided
                            if progress_callback:
                                import re

                                percent_match = re.search(
                                    r"(\d+)\s*%", line, re.IGNORECASE
                                )
                                if percent_match:
                                    try:
                                        percent = int(percent_match.group(1))
                                        progress_callback(percent / 100.0)
                                    except (ValueError, TypeError):
                                        pass
                        # Filter out very verbose Wine debug messages but keep important ones
                        elif not any(
                            skip in line_lower
                            for skip in ["fixme:", "trace:", "debug:"]
                        ):
                            # Show other non-debug messages
                            self.log(f"  {line}", "info")

            process.wait()
            self._last_stream_output_text = "".join(buffer)
            return process.returncode == 0
        except Exception as e:
            self.log(f"Error running command: {e}", "error")
            return False
        finally:
            try:
                self._unregister_process(process)
            except Exception:
                pass

    def _to_windows_path(self, unix_path, env=None):
        """Convert a UNIX path to a Windows path for Wine 'start' using winepath.
        Falls back to Z: drive mapping if winepath is unavailable."""
        try:
            winepath_bin = self.get_wine_path("winepath")
            if winepath_bin.exists():
                success, stdout, _ = self.run_command(
                    [str(winepath_bin), "-w", str(unix_path)],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success and stdout:
                    return stdout.strip().splitlines()[-1]
        except Exception:
            pass
        # Fallback: Z: mapping
        p = str(unix_path)
        if p.startswith("/"):
            win = "Z:" + p
        else:
            win = p
        return win.replace("/", "\\")

    def _has_installer_activity(self, installer_file: Path) -> bool:
        """Heuristics to detect installer activity:
        - Check for Wine processes referencing installer/common names
        - If wmctrl is available, check for visible windows with class/name containing wine/setup/installer
        """
        try:
            # Process-based heuristic
            patterns = [
                installer_file.name.lower(),
                "setup",
                "msiexec",
                "install",
                ".msi",
                ".exe",
            ]
            success, stdout, _ = self.run_command(
                ["ps", "-eo", "pid,command"], check=False, capture=True
            )
            if success and stdout:
                text = stdout.lower()
                if ("wine" in text or "wineserver" in text) and any(
                    pat in text for pat in patterns
                ):
                    return True
            # Window-based heuristic (wmctrl)
            wmctrl = shutil.which("wmctrl")
            if wmctrl:
                ok, wout, _ = self.run_command(
                    [wmctrl, "-lx"], check=False, capture=True
                )
                if ok and wout:
                    w = wout.lower()
                    # Examples: 'wine.wine explorer.exe', 'setup.exe', 'affinity'
                    if "wine" in w and any(pat in w for pat in patterns):
                        return True
        except Exception:
            pass
        return False

    def _run_installer_and_capture(
        self, installer_file: Path, env: dict, label: str = "installer"
    ):
        """Run a Windows installer under Wine, stream logs, and wait robustly until it exits.
        Strategy:
        1) Try 'wine start /wait /unix <file>'
        2) If it exits too quickly or returns non-zero with no activity, try 'wine <file>'
        3) After launch, wait on 'wineserver -w' to ensure child processes finish (cancellable)

        For Affinity v3, uses system wine instead of patched wine.
        """
        # Check if this is Affinity v3 or WebView2 installer
        installer_name = installer_file.name.lower()
        is_affinity_v3 = "affinity" in installer_name and (
            "x64" in installer_name or "affinity-x64" in installer_name
        )
        is_affinity_v2 = (
            any(app in installer_name for app in ["photo", "designer", "publisher"])
            and ".exe" in installer_name
        )
        is_webview2 = "webview" in installer_name or "edge" in installer_name

        # Set Windows 11 before installing Affinity
        if is_affinity_v3 or is_affinity_v2:
            self.log(
                "Setting Windows version to 11 before Affinity installation...", "info"
            )
            # Use system winecfg for Affinity installers (they use system wine)
            self.run_command(["winecfg", "-v", "win11"], check=False, env=env)
            self.log("✓ Windows version set to 11", "success")

        # Use system Wine for Affinity installations (custom Wine doesn't work for installation)
        if is_affinity_v3 or is_affinity_v2:
            wine = "wine"  # Use system Wine for installation
            self.log("Using system Wine for Affinity installation", "info")
        elif is_webview2:
            # Use system wine for WebView2
            wine = "wine"
            self.log("Using system Wine for WebView2 installation", "info")
        else:
            # Use custom Wine for other installers
            wine = str(self.get_wine_path("wine"))

        # For Affinity installers, try direct execution first (more reliable)
        if is_affinity_v3 or is_affinity_v2:
            attempts = [
                [wine, str(installer_file)],
                [wine, "start", "/wait", "/unix", str(installer_file)],
            ]
        else:
            attempts = [
                [wine, "start", "/wait", "/unix", str(installer_file)],
                [wine, str(installer_file)],
            ]
        for idx, cmd in enumerate(attempts, start=1):
            try:
                cmd_str = " ".join(shlex.quote(c) for c in cmd)
                self.log(f"Running ({label}) attempt {idx}: {cmd_str}", "info")
                t0 = time.time()
                ok = self.run_command_streaming(cmd, env=env)
                dt = time.time() - t0

                # For Affinity installers, check if installer is actually running despite exceptions
                if is_affinity_v3 or is_affinity_v2:
                    txt = (self._last_stream_output_text or "").lower()
                    # Check if we got a debugger exception but installer might still be running
                    if "unhandled exception" in txt or "winedbg" in txt:
                        self.log(
                            "Wine debugger exception detected, checking if installer is running...",
                            "warning",
                        )
                        # Give it a moment to start
                        time.sleep(3)
                        if self._has_installer_activity(installer_file):
                            self.log(
                                "Installer is running despite exception message, continuing...",
                                "info",
                            )
                            ok = True

                # If it "succeeded" unrealistically fast, poll briefly for activity or window
                if ok and dt < 5.0:
                    self.log(
                        f"{label.capitalize()} attempt {idx} returned quickly ({dt:.2f}s). Polling for activity...",
                        "warning",
                    )
                    for _ in range(30):  # ~3s
                        if self.check_cancelled():
                            return False
                        if self._has_installer_activity(installer_file):
                            break
                        time.sleep(0.1)
                    else:
                        ok = False
                # Also verify there was some wine activity (best-effort heuristic)
                if ok and not self._has_installer_activity(installer_file):
                    # As a last signal, check stream output for obvious errors
                    txt = (self._last_stream_output_text or "").lower()
                    error_markers = [
                        "err:",
                        "cannot find",
                        "bad exe",
                        "failed",
                        "error:",
                        "no such file",
                        "unable to load",
                    ]
                    # For Affinity installers, ignore debugger messages if installer is running
                    if is_affinity_v3 or is_affinity_v2:
                        # Double-check if installer is actually running
                        time.sleep(1)
                        if self._has_installer_activity(installer_file):
                            ok = True  # Installer is running, ignore error markers
                    if any(m in txt for m in error_markers) and not (
                        is_affinity_v3
                        or is_affinity_v2
                        and self._has_installer_activity(installer_file)
                    ):
                        ok = False
                # For Affinity installers, even if ok is False, check if installer is actually running
                if (is_affinity_v3 or is_affinity_v2) and not ok:
                    # Check one more time if installer is running
                    time.sleep(2)
                    if self._has_installer_activity(installer_file):
                        self.log(
                            "Installer is running despite error, continuing...", "info"
                        )
                        ok = True

                if ok:
                    # For WebView2, use polling with timeout instead of indefinite wineserver wait
                    if is_webview2:
                        self.log(
                            "Waiting for WebView2 installer to complete (polling with timeout)...",
                            "info",
                        )
                        max_wait_time = 600  # 10 minutes max
                        poll_interval = 2  # Check every 2 seconds
                        start_time = time.time()

                        while time.time() - start_time < max_wait_time:
                            if self.check_cancelled():
                                return False

                            # Check if installer process/window is still active
                            if not self._has_installer_activity(installer_file):
                                # No installer activity - wait a bit more to ensure it's really done
                                time.sleep(3)
                                # Double-check it's still inactive
                                if not self._has_installer_activity(installer_file):
                                    # Also verify WebView2 was actually installed
                                    webview2_paths = [
                                        Path(self.directory)
                                        / "drive_c"
                                        / "Program Files (x86)"
                                        / "Microsoft"
                                        / "EdgeWebView"
                                        / "Application",
                                        Path(self.directory)
                                        / "drive_c"
                                        / "Program Files"
                                        / "Microsoft"
                                        / "EdgeWebView"
                                        / "Application",
                                    ]
                                    installed = any(
                                        (path / "msedgewebview2.exe").exists()
                                        for path in webview2_paths
                                    )
                                    if installed:
                                        self.log(
                                            "WebView2 installer completed and files detected",
                                            "success",
                                        )
                                    else:
                                        self.log(
                                            "WebView2 installer appears to have completed (files not yet detected)",
                                            "info",
                                        )
                                    break

                            time.sleep(poll_interval)
                        else:
                            self.log(
                                "WebView2 installer timeout reached - proceeding anyway",
                                "warning",
                            )

                        # Final wineserver wait with short timeout
                        env_wait = env.copy() if env else os.environ.copy()
                        env_wait["WINEPREFIX"] = self.directory
                        try:
                            # Use timeout for wineserver wait (30 seconds max)
                            process = subprocess.Popen(
                                ["wineserver", "-w"],
                                env=env_wait,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            self.log(
                                "Wineserver wait timed out - installer may have finished",
                                "warning",
                            )
                            process.kill()
                        except Exception as e:
                            self.log(
                                f"Wineserver wait error (non-critical): {e}", "warning"
                            )
                    else:
                        self.log(
                            "Waiting for Wine processes to finish (wineserver -w)...",
                            "info",
                        )
                        # Extended wait; cancellable via run_command loop
                        env_wait = env.copy() if env else os.environ.copy()
                        env_wait["WINEPREFIX"] = self.directory
                        # Use system wineserver (always use system wineserver, not patched one)
                        self.run_command(
                            ["wineserver", "-w"],
                            check=False,
                            capture=False,
                            env=env_wait,
                        )
                    return True
                if self.check_cancelled():
                    return False
                self.log(
                    f"{label.capitalize()} attempt {idx} did not run (ok={ok}, dt={dt:.2f}s). Trying fallback...",
                    "warning",
                )
            except Exception as e:
                self.log(f"Error launching {label} attempt {idx}: {e}", "error")
        return False

    def run_command_interactive(self, command, env=None):
        """Execute command and handle interactive prompts via GUI, cancellable."""
        try:
            if isinstance(command, str):
                command = command.split()

            # Set up environment for non-interactive operation
            if env is None:
                env = os.environ.copy()

            # Force non-interactive mode for various tools
            env["DEBIAN_FRONTEND"] = "noninteractive"
            env["NEEDRESTART_MODE"] = "a"
            env["DEBIAN_PRIORITY"] = "critical"
            env["APT_LISTCHANGES_FRONTEND"] = "none"
            env["LANG"] = "C"
            env["LC_ALL"] = "C"

            # Check if this is a sudo command
            is_sudo = (
                isinstance(command, list) and len(command) > 0 and command[0] == "sudo"
            )

            # Unset SUDO_ASKPASS to force sudo to read password from stdin via -S flag
            # This prevents errors when askpass programs (like ksshaskpass) don't exist
            if is_sudo:
                env.pop("SUDO_ASKPASS", None)

            if is_sudo:
                # Get password if needed
                password = self.get_sudo_password()
                if password is None:
                    self.log("Authentication cancelled by user", "warning")
                    return False, "", "Authentication cancelled"

                # Validate password if not already validated
                if not self.sudo_password_validated:
                    if not self.validate_sudo_password(password):
                        self.log("Authentication failed", "error")
                        return False, "", "Authentication failed"

                # Add -S flag if not present
                # Create a copy to avoid modifying the original
                command = list(command)
                if len(command) > 1:
                    if command[1] != "-S":
                        # Remove -S if it exists elsewhere (safely)
                        while "-S" in command:
                            command.remove("-S")
                        # Insert -S right after "sudo"
                        command.insert(1, "-S")
                else:
                    # Only "sudo" in command, add -S
                    command.append("-S")

            # Start process
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                preexec_fn=os.setsid,
            )
            self._register_process(process)

            # If sudo, send password first
            if is_sudo and self.sudo_password:
                try:
                    process.stdin.write(f"{self.sudo_password}\n")
                    process.stdin.flush()
                except Exception:
                    pass

            # Read output and detect prompts
            output_lines = []
            error_lines = []

            import select

            while True:
                if self.cancel_event.is_set():
                    self._terminate_process(process)
                    return False, "", "Cancelled"
                # Check if process has finished
                if process.poll() is not None:
                    # Read any remaining output
                    remaining_out = process.stdout.read()
                    remaining_err = process.stderr.read()
                    if remaining_out:
                        output_lines.append(remaining_out)
                    if remaining_err:
                        error_lines.append(remaining_err)
                    break

                # Try to read from stdout with timeout
                try:
                    # Use select to check if data is available (Unix-like systems)
                    import sys

                    if hasattr(select, "select"):
                        readable, _, _ = select.select(
                            [process.stdout, process.stderr], [], [], 0.1
                        )

                        for stream in readable:
                            line = stream.readline()
                            if line:
                                if stream == process.stdout:
                                    output_lines.append(line)
                                    self.log(f"  {line.rstrip()}", "info")
                                else:
                                    error_lines.append(line)

                                # Detect interactive prompts
                                line_lower = line.lower()
                                if any(
                                    pattern in line_lower
                                    for pattern in [
                                        "overwrite?",
                                        "(y/n)",
                                        "[y/n]",
                                        "yes/no",
                                        "continue?",
                                        "proceed?",
                                        "replace?",
                                    ]
                                ):
                                    # Interactive prompt detected!
                                    self.log(
                                        f"Interactive prompt detected: {line.rstrip()}",
                                        "warning",
                                    )

                                    # Extract default response if present
                                    default = ""
                                    if "(y/n)" in line_lower:
                                        # Check which is capitalized
                                        if "(Y/n)" in line:
                                            default = "y"
                                        elif "(y/N)" in line:
                                            default = "n"

                                    # Get user response via GUI
                                    response = self.get_interactive_response(
                                        line.rstrip(), default
                                    )

                                    # Send response to process
                                    if process.stdin:
                                        process.stdin.write(response)
                                        process.stdin.flush()
                except Exception as e:
                    self.log(f"Error reading process output: {e}", "warning")
                    time.sleep(0.1)

            # Get return code
            return_code = process.wait()

            stdout_text = "".join(output_lines)
            stderr_text = "".join(error_lines)

            return return_code == 0, stdout_text, stderr_text

        except Exception as e:
            self.log(f"Error in interactive command: {e}", "error")
            return False, "", str(e)
        finally:
            try:
                self._unregister_process(process)
            except Exception:
                pass

    def check_command(self, cmd):
        """Check if command exists"""
        return shutil.which(cmd) is not None

    def detect_distro(self):
        """Detect Linux distribution"""
        try:
            with open("/etc/os-release", "r") as f:
                content = f.read()

            for line in content.split("\n"):
                if line.startswith("ID="):
                    self.distro = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION_ID="):
                    self.distro_version = line.split("=", 1)[1].strip().strip('"')

            # Normalize "pika" to "pikaos" if detected
            if self.distro == "pika":
                self.distro = "pikaos"

            # Normalize "pop" to "pop" if detected
            if self.distro == "pop":
                self.distro = "pop"

            return True
        except Exception as e:
            self.log(f"Error detecting distribution: {e}", "error")
            return False

    def _ensure_icons_directory(self):
        """Ensure icons directory exists, download from GitHub if missing (optimized)"""
        try:
            # Always use the standard location in user's config directory
            # This ensures icons are available even when script is piped from curl
            script_dir = Path.home() / ".config" / "AffinityOnLinux" / "AffinityScripts"
            script_dir.mkdir(parents=True, exist_ok=True)

            icons_dir = script_dir / "icons"

            # Ensure icons directory exists
            icons_dir.mkdir(parents=True, exist_ok=True)

            # Check if local icons directory exists and has icons (fast path)
            local_icons_dir = Path(__file__).parent / "icons"
            if local_icons_dir.exists():
                # If local icons exist, copy them quickly instead of downloading
                try:
                    local_icons = list(local_icons_dir.glob("*.svg"))
                    if local_icons:
                        # Copy missing icons from local directory
                        for local_icon in local_icons:
                            dest_icon = icons_dir / local_icon.name
                            if not dest_icon.exists():
                                shutil.copy2(local_icon, dest_icon)
                        return  # Fast path - use local icons
                except Exception:
                    pass  # Fall through to download if copy fails

            # List of UI theme icons to download from GitHub (only if local icons don't exist)
            # Note: Application icons (Affinity.png, etc.) are downloaded elsewhere
            # These are just the UI button icons needed for the installer interface
            icon_files = [
                # Zoom icons
                ("zoom-in-dark.svg", "AffinityScripts/icons/zoom-in-dark.svg"),
                ("zoom-in-light.svg", "AffinityScripts/icons/zoom-in-light.svg"),
                ("zoom-out-dark.svg", "AffinityScripts/icons/zoom-out-dark.svg"),
                ("zoom-out-light.svg", "AffinityScripts/icons/zoom-out-light.svg"),
                (
                    "zoom-original-dark.svg",
                    "AffinityScripts/icons/zoom-original-dark.svg",
                ),
                (
                    "zoom-original-light.svg",
                    "AffinityScripts/icons/zoom-original-light.svg",
                ),
                # Action icons
                ("rocket-dark.svg", "AffinityScripts/icons/rocket-dark.svg"),
                ("rocket-light.svg", "AffinityScripts/icons/rocket-light.svg"),
                ("wine-dark.svg", "AffinityScripts/icons/wine-dark.svg"),
                ("wine-light.svg", "AffinityScripts/icons/wine-light.svg"),
                (
                    "dependencies-dark.svg",
                    "AffinityScripts/icons/dependencies-dark.svg",
                ),
                (
                    "dependencies-light.svg",
                    "AffinityScripts/icons/dependencies-light.svg",
                ),
                ("wand-dark.svg", "AffinityScripts/icons/wand-dark.svg"),
                ("wand-light.svg", "AffinityScripts/icons/wand-light.svg"),
                ("download-dark.svg", "AffinityScripts/icons/download-dark.svg"),
                ("download-light.svg", "AffinityScripts/icons/download-light.svg"),
                ("folderopen-dark.svg", "AffinityScripts/icons/folderopen-dark.svg"),
                ("folderopen-light.svg", "AffinityScripts/icons/folderopen-light.svg"),
                ("camera-dark.svg", "AffinityScripts/icons/camera-dark.svg"),
                ("camera-light.svg", "AffinityScripts/icons/camera-light.svg"),
                ("pen-dark.svg", "AffinityScripts/icons/pen-dark.svg"),
                ("pen-light.svg", "AffinityScripts/icons/pen-light.svg"),
                ("book-dark.svg", "AffinityScripts/icons/book-dark.svg"),
                ("book-light.svg", "AffinityScripts/icons/book-light.svg"),
                ("windows-dark.svg", "AffinityScripts/icons/windows-dark.svg"),
                ("windows-light.svg", "AffinityScripts/icons/windows-light.svg"),
                ("display-dark.svg", "AffinityScripts/icons/display-dark.svg"),
                ("display-light.svg", "AffinityScripts/icons/display-light.svg"),
                ("lightning-dark.svg", "AffinityScripts/icons/lightning-dark.svg"),
                ("lightning-light.svg", "AffinityScripts/icons/lightning-light.svg"),
                ("loop-dark.svg", "AffinityScripts/icons/loop-dark.svg"),
                ("loop-light.svg", "AffinityScripts/icons/loop-light.svg"),
                ("chrome-dark.svg", "AffinityScripts/icons/chrome-dark.svg"),
                ("chrome-light.svg", "AffinityScripts/icons/chrome-light.svg"),
                ("cog-dark.svg", "AffinityScripts/icons/cog-dark.svg"),
                ("cog-light.svg", "AffinityScripts/icons/cog-light.svg"),
                ("scale-dark.svg", "AffinityScripts/icons/scale-dark.svg"),
                ("scale-light.svg", "AffinityScripts/icons/scale-light.svg"),
                ("trash-dark.svg", "AffinityScripts/icons/trash-dark.svg"),
                ("trash-light.svg", "AffinityScripts/icons/trash-light.svg"),
                ("play-dark.svg", "AffinityScripts/icons/play-dark.svg"),
                ("play-light.svg", "AffinityScripts/icons/play-light.svg"),
                ("exit-dark.svg", "AffinityScripts/icons/exit-dark.svg"),
                ("exit-light.svg", "AffinityScripts/icons/exit-light.svg"),
                (
                    "affinity-unified-dark.svg",
                    "AffinityScripts/icons/affinity-unified-dark.svg",
                ),
                (
                    "affinity-unified-light.svg",
                    "AffinityScripts/icons/affinity-unified-light.svg",
                ),
            ]

            # Check which icons are missing
            missing_icons = []
            for local_name, github_path in icon_files:
                icon_path = icons_dir / local_name
                if not icon_path.exists():
                    missing_icons.append((local_name, github_path))

            # Only download if there are missing icons
            if not missing_icons:
                return  # All icons already exist

            # Download icons in parallel for speed (no log messages)
            base_url = "https://raw.githubusercontent.com/seapear/AffinityOnLinux/main/"

            def download_icon(local_name, github_path):
                """Download a single icon"""
                icon_path = icons_dir / local_name
                try:
                    # Check if github_path is a full URL (for user-attachments) or relative path
                    if github_path.startswith("http://") or github_path.startswith(
                        "https://"
                    ):
                        icon_url = github_path
                    else:
                        icon_url = base_url + github_path

                    # Use urlretrieve with timeout
                    urllib.request.urlretrieve(icon_url, str(icon_path))
                except Exception:
                    # Silently fail - icons are not critical for functionality
                    pass

            # Download icons in parallel (limit to 5 concurrent downloads to avoid overwhelming)
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=5) as executor:
                executor.map(lambda args: download_icon(*args), missing_icons)
        except Exception:
            # Silently fail - icons are not critical for functionality
            pass

    def detect_gpus(self):
        """Detect available GPUs in the system"""
        gpus = []

        # Get lspci output once
        lspci_success, lspci_stdout, _ = self.run_command(
            ["lspci"], check=False, capture=True
        )
        if not lspci_success or not lspci_stdout:
            # If lspci fails, return auto option only
            gpus.append(
                {
                    "type": "auto",
                    "name": "Auto (System Default)",
                    "index": 0,
                    "id": "auto",
                }
            )
            return gpus

        # Parse lspci output to find actual GPU devices
        # Look for VGA, 3D, or Display controller entries
        gpu_lines = []
        for line in lspci_stdout.split("\n"):
            line_lower = line.lower()
            # Check if this is a graphics/display device
            # GREP defined more explicitly, avoids wrong lines
            if any(
                keyword in line_lower
                for keyword in [
                    "vga",
                    "3d controller",
                    "display controller",
                    "graphics",
                ]
            ):
                gpu_lines.append(line)

        # Process each GPU line to extract type and model
        for line in gpu_lines:
            line_lower = line.lower()

            # Extract model name (everything after the last colon)
            if ":" in line:
                model = (
                    line.split(":")[2].strip()
                    if len(line.split(":")) > 2
                    else "Unknown GPU"
                )
            else:
                model = "Unknown GPU"

            # Determine GPU type
            gpu_type = None
            gpu_id = None

            if "nvidia" in line_lower:
                gpu_type = "nvidia"
                # Count existing nvidia GPUs to get index
                nvidia_count = sum(1 for gpu in gpus if gpu["type"] == "nvidia")
                gpu_id = f"nvidia_{nvidia_count}"
            elif (
                "amd" in line_lower or "radeon" in line_lower or "amd/ati" in line_lower
            ):
                gpu_type = "amd"
                amd_count = sum(1 for gpu in gpus if gpu["type"] == "amd")
                gpu_id = f"amd_{amd_count}"
            elif "intel" in line_lower:
                gpu_type = "intel"
                intel_count = sum(1 for gpu in gpus if gpu["type"] == "intel")
                gpu_id = f"intel_{intel_count}"

            # Only add if we identified a GPU type
            if gpu_type:
                gpus.append(
                    {
                        "type": gpu_type,
                        "name": model,
                        "index": len([g for g in gpus if g["type"] == gpu_type]),
                        "id": gpu_id,
                    }
                )

        # Always add "Auto" option as the first choice
        gpus.insert(
            0,
            {"type": "auto", "name": "Auto (System Default)", "index": 0, "id": "auto"},
        )

        return gpus

    def has_amd_gpu(self):
        """Check if system has an AMD GPU"""
        gpus = self.detect_gpus()
        return any(gpu["type"] == "amd" for gpu in gpus)

    def has_nvidia_gpu(self):
        """Check if system has an NVIDIA GPU"""
        gpus = self.detect_gpus()
        return any(gpu["type"] == "nvidia" for gpu in gpus)

    def get_selected_gpu(self):
        """Get environment variables for GPU selection"""
        gpu_config_file = Path(self.directory) / ".gpu_config"
        gpu_id = "auto"
        if gpu_config_file.exists():
            try:
                with open(gpu_config_file, "r") as f:
                    gpu_id = f.read().strip()
            except Exception:
                gpu_id = "auto"
        return gpu_id

    def get_dxvk_vkd3d_preference(self):
        """Get DXVK/vkd3d preference for NVIDIA users"""
        pref_file = Path(self.directory) / ".dxvk_vkd3d_preference"
        if pref_file.exists():
            try:
                with open(pref_file, "r") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def set_dxvk_vkd3d_preference(self, preference):
        """Set DXVK/vkd3d preference for NVIDIA users (either 'dxvk' or 'vkd3d')"""
        pref_file = Path(self.directory) / ".dxvk_vkd3d_preference"
        try:
            with open(pref_file, "w") as f:
                f.write(preference)
            return True
        except Exception as e:
            self.log(f"Failed to save DXVK/vkd3d preference: {e}", "error")
            return False

    def _show_nvidia_dxvk_vkd3d_choice_safe(self):
        """Show NVIDIA DXVK/vkd3d choice dialog (called from main thread)"""
        # Check if preference already exists
        existing_pref = self.get_dxvk_vkd3d_preference()
        if existing_pref in ["dxvk", "vkd3d"]:
            self.nvidia_dxvk_vkd3d_choice_response = existing_pref
            self.waiting_for_nvidia_choice = False
            return

        # Create a custom dialog
        dialog = QDialog()
        dialog.setWindowTitle("Choose Graphics Backend for NVIDIA GPU")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing - improved for all screen sizes
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(300, int(screen_height * 0.7))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(350, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 450
            min_height = 320
            default_width = 550
            default_height = 380
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 450
            min_height = 320
            default_width = 550
            default_height = 380
            max_width = 800
            max_height = 700

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet matching main UI
        if self.dark_mode:
            dialog_style = """
                QDialog {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed {
                    background-color: #3db9a0;
                }
            """
        else:
            dialog_style = """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 12px;
                    color: #666666;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 14px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#okButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#okButton:pressed {
                    background-color: #3d8b40;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """

        dialog.setStyleSheet(dialog_style)

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("NVIDIA GPU Detected")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Please choose your preferred graphics backend:\n\n"
            "• <b>vkd3d</b> - Includes OpenCL support for hardware acceleration\n"
            "• <b>DXVK</b> - Hardware accelerated, uses the GPU (no OpenCL)\n\n"
            "Note: You can change this later if needed."
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        # Radio buttons in styled frames
        button_group = QButtonGroup()

        # vkd3d option
        vkd3d_frame = QFrame()
        vkd3d_frame.setObjectName("optionFrame")
        vkd3d_layout = QVBoxLayout(vkd3d_frame)
        vkd3d_layout.setContentsMargins(12, 10, 12, 10)
        vkd3d_radio = QRadioButton("vkd3d (with OpenCL support)")
        vkd3d_radio.setChecked(True)
        vkd3d_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        vkd3d_layout.addWidget(vkd3d_radio)
        options_layout.addWidget(vkd3d_frame)

        # DXVK option
        dxvk_frame = QFrame()
        dxvk_frame.setObjectName("optionFrame")
        dxvk_layout = QVBoxLayout(dxvk_frame)
        dxvk_layout.setContentsMargins(12, 10, 12, 10)
        dxvk_radio = QRadioButton("DXVK (hardware accelerated, no OpenCL)")
        dxvk_radio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        dxvk_layout.addWidget(dxvk_radio)
        options_layout.addWidget(dxvk_frame)

        button_group.addButton(vkd3d_radio, 0)
        button_group.addButton(dxvk_radio, 1)

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        # Get result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if vkd3d_radio.isChecked():
                preference = "vkd3d"
            else:
                preference = "dxvk"

            self.set_dxvk_vkd3d_preference(preference)
            self.nvidia_dxvk_vkd3d_choice_response = preference
        else:
            # User cancelled - default to vkd3d
            self.set_dxvk_vkd3d_preference("vkd3d")
            self.nvidia_dxvk_vkd3d_choice_response = "vkd3d"

        self.waiting_for_nvidia_choice = False

    def ask_nvidia_dxvk_vkd3d_choice(self):
        """Ask NVIDIA users to choose between DXVK and vkd3d (thread-safe)"""
        # Check if preference already exists
        existing_pref = self.get_dxvk_vkd3d_preference()
        if existing_pref in ["dxvk", "vkd3d"]:
            return existing_pref

        # Show dialog using signal (thread-safe)
        self.nvidia_dxvk_vkd3d_choice_response = None
        self.waiting_for_nvidia_choice = True
        self.nvidia_dxvk_vkd3d_choice_signal.emit()

        # Wait for response with timeout
        max_wait = 300  # 30 seconds
        waited = 0
        while self.waiting_for_nvidia_choice and waited < max_wait:
            time.sleep(0.1)
            waited += 1

        return self.nvidia_dxvk_vkd3d_choice_response or "vkd3d"

    def get_gpu_env_vars(self, gpu_id=None):
        """Get environment variables for GPU selection"""
        if gpu_id is None:
            # Load from saved preference
            gpu_config_file = Path(self.directory) / ".gpu_config"
            if gpu_config_file.exists():
                try:
                    with open(gpu_config_file, "r") as f:
                        gpu_id = f.read().strip()
                except Exception:
                    gpu_id = "auto"
            else:
                gpu_id = "auto"

        env_vars = []

        if gpu_id == "auto" or not gpu_id:
            # No specific GPU selection - use system default
            return ""

        if gpu_id.startswith("nvidia_"):
            # NVIDIA GPU selection
            env_vars.append("__NV_PRIME_RENDER_OFFLOAD=1")
            env_vars.append("__GLX_VENDOR_LIBRARY_NAME=nvidia")
            # Also set for Vulkan
            env_vars.append("__VK_LAYER_NV_optimus=NVIDIA_only")

        elif gpu_id.startswith("amd_"):
            # AMD discrete GPU (using DRI_PRIME)
            index = int(gpu_id.split("_")[1]) if "_" in gpu_id else 1
            env_vars.append(f"DRI_PRIME={index}")

        elif gpu_id.startswith("intel_"):
            # Intel GPU (usually integrated, use DRI_PRIME=0)
            env_vars.append("DRI_PRIME=0")

        if env_vars:
            return " ".join(env_vars) + " "
        return ""

    def get_current_backend(self):
        """Detect which graphics backend is currently being used (dxvk or vkd3d)"""
        # Check preference first (applies to all GPU types)
        preference = self.get_dxvk_vkd3d_preference()
        if preference == "dxvk":
            return "dxvk"
        elif preference == "vkd3d":
            return "vkd3d"

        # If no preference set, check if vkd3d DLLs exist
        wine_lib_dir = (
            self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
        )
        if wine_lib_dir.exists() and (wine_lib_dir / "d3d12.dll").exists():
            return "vkd3d"

        # Default to DXVK (for AMD, NVIDIA, and other GPUs)
        return "dxvk"

    def get_dxvk_env_vars(self):
        """Get DXVK environment variables for AMD GPU or NVIDIA GPU with DXVK preference"""
        gpu_id = self.get_selected_gpu()
        if self.has_nvidia_gpu() and (
            gpu_id.startswith("nvidia_") or gpu_id.startswith("auto")
        ):
            preference = self.get_dxvk_vkd3d_preference()
            if preference == "dxvk":
                return 'DXVK_ASYNC=0 DXVK_CONFIG="d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1" '
        elif self.has_amd_gpu() and (
            gpu_id.startswith("amd_") or gpu_id.startswith("auto")
        ):
            return 'DXVK_ASYNC=0 DXVK_CONFIG="d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1" '
        return ""

    def _configure_gpu_selection_safe(self):
        """Configure GPU selection for dual GPU setups (safe UI slot)"""
        gpus = self.detect_gpus()

        if len(gpus) <= 1:
            self.show_message(
                "GPU Selection",
                "Only one GPU detected or no GPUs found.\n\n"
                "GPU selection is only needed for dual GPU setups.\n"
                "Your system will use the default GPU automatically.",
                "info",
            )
            # Ensure waiting flag is cleared for background callers
            try:
                self.waiting_for_gpu_selection = False
            except Exception:
                pass
            return

        # Load current selection
        gpu_config_file = Path(self.directory) / ".gpu_config"
        current_gpu = "auto"
        if gpu_config_file.exists():
            try:
                with open(gpu_config_file, "r") as f:
                    current_gpu = f.read().strip()
            except Exception:
                pass

        # Create dialog for GPU selection (without parent to avoid threading issues)
        dialog = QDialog()
        dialog.setWindowTitle("GPU Selection for Affinity Applications")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(300, int(screen_height * 0.8))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(350, int(screen_height * 0.7))
        else:
            min_width = 450
            min_height = 320
            default_width = 550
            default_height = 380

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("GPU Selection for Affinity Applications")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Select which GPU to use for Affinity applications:\n\n"
            "This is useful for dual GPU setups (e.g., Intel + NVIDIA, AMD + NVIDIA).\n"
            "If you want to enable OpenCL and have a NVIDIA GPU, it's recommended to select it for better compatibility.\n"
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        # Create radio buttons for each GPU
        button_group = QButtonGroup(dialog)
        radio_buttons = []

        # Add "Auto" option first
        auto_frame = QFrame()
        auto_frame.setObjectName("optionFrame")
        auto_layout = QVBoxLayout(auto_frame)
        auto_layout.setContentsMargins(12, 10, 12, 10)
        auto_radio = QRadioButton("Auto (System Default)")
        auto_radio.setChecked(current_gpu == "auto")
        auto_radio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        auto_layout.addWidget(auto_radio)
        options_layout.addWidget(auto_frame)
        button_group.addButton(auto_radio, -1)
        radio_buttons.append(("auto", auto_radio))

        # Add detected GPUs
        for gpu in gpus:
            if gpu["id"] != "auto":  # Skip if it's the auto placeholder
                gpu_frame = QFrame()
                gpu_frame.setObjectName("optionFrame")
                gpu_layout = QVBoxLayout(gpu_frame)
                gpu_layout.setContentsMargins(12, 10, 12, 10)
                gpu_label = f"{gpu['name']} ({gpu['type'].upper()})"
                radio = QRadioButton(gpu_label)
                radio.setChecked(current_gpu == gpu["id"])
                radio.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
                )
                gpu_layout.addWidget(radio)
                options_layout.addWidget(gpu_frame)
                button_group.addButton(radio, gpus.index(gpu))
                radio_buttons.append((gpu["id"], radio))

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_id = None
            for gpu_id, radio in radio_buttons:
                if radio.isChecked():
                    selected_id = gpu_id
                    break

            if selected_id:
                self.question_dialog_response = selected_id
                # Save selection
                try:
                    with open(gpu_config_file, "w") as f:
                        f.write(selected_id)

                    gpu_name = next(
                        (gpu["name"] for gpu in gpus if gpu["id"] == selected_id),
                        "Auto",
                    )
                    self.log(f"GPU selection saved: {gpu_name}", "success")

                    # Update existing desktop entries
                    self.update_existing_desktop_entries()

                    self.show_message(
                        "GPU Selection Saved",
                        f"Selected GPU: {gpu_name}\n\n"
                        "All existing desktop entries have been updated with the new GPU configuration.",
                        "info",
                    )
                except Exception as e:
                    self.log(f"Failed to save GPU selection: {e}", "error")
        else:
            # User cancelled - return "Cancel" to match expected format
            self.question_dialog_response = "Cancel"

        self.waiting_for_question_response = False
        self.waiting_for_gpu_selection = False

    def configure_gpu_selection(self):
        """Ask user to select GPU for dual-GPU setups (thread-safe)"""
        self.waiting_for_gpu_selection = True
        self.gpu_selection_signal.emit()

        # Block the calling thread until the main thread finishes the dialog
        max_wait = 3000  # 5 minutes max wait
        waited = 0
        while self.waiting_for_gpu_selection and waited < max_wait:
            import time

            time.sleep(0.1)
            waited += 1

    def get_switch_backend_button_text(self):
        """Get the text for the switch backend button based on current backend"""
        current = self.get_current_backend()
        if current == "dxvk":
            return "Switch to VKD3D"
        else:
            return "Switch to DXVK"

    def get_switch_backend_tooltip(self):
        """Get the tooltip for the switch backend button based on current backend"""
        current = self.get_current_backend()
        if current == "dxvk":
            return "Switch from DXVK to VKD3D (includes OpenCL support)"
        else:
            return "Switch from VKD3D to DXVK for graphics acceleration"

    def update_switch_backend_button(self):
        """Update the switch backend button text and tooltip"""
        if self.switch_backend_button:
            self.switch_backend_button.setText(self.get_switch_backend_button_text())
            self.switch_backend_button.setToolTip(self.get_switch_backend_tooltip())

    def switch_graphics_backend(self):
        """Switch between DXVK and VKD3D based on current backend"""
        current = self.get_current_backend()
        if current == "dxvk":
            self.switch_to_vkd3d()
        else:
            self.switch_to_dxvk()

    def switch_to_vkd3d(self):
        """Switch from DXVK to VKD3D, installing vkd3d-proton"""
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Switch to VKD3D",
            "This will:\n\n"
            "• Install vkd3d-proton for OpenCL support\n"
            "• Install d3d12.dll and d3d12core.dll\n"
            "• Set preference to use VKD3D\n"
            "• Update all desktop entries to remove DXVK environment variables\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Switching to VKD3D", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        try:
            # 1. Install vkd3d-proton (full setup)
            self.log("Installing vkd3d-proton...", "info")
            self.setup_vkd3d()

            # 2. Set preference to VKD3D
            self.set_dxvk_vkd3d_preference("vkd3d")
            self.log("Set preference to VKD3D", "success")

            # 3. Remove DXVK DLL overrides and DLLs from system32 (if any)
            self.remove_dxvk_overrides()

            # 4. Set up DLL overrides for vkd3d
            self.log("Setting up DLL overrides for vkd3d...", "info")
            self.setup_d3d12_overrides()

            # 5. Copy DLLs to application directories
            self.log("Copying d3d12 DLLs to application directories...", "info")
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            vkd3d_temp = Path(self.directory) / "vkd3d_dlls"

            app_dirs = {
                "Photo": "Photo 2",
                "Designer": "Designer 2",
                "Publisher": "Publisher 2",
                "Add": "Affinity",
            }

            for app_name, app_dir_name in app_dirs.items():
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / app_dir_name
                )
                if app_dir.exists():
                    for dll in ["d3d12.dll", "d3d12core.dll"]:
                        for source in [wine_lib_dir / dll, vkd3d_temp / dll]:
                            if source.exists():
                                shutil.copy2(source, app_dir / dll)
                                self.log(f"Copied {dll} to {app_dir_name}", "success")
                                break

            # 6. Update all desktop entries (remove DXVK env vars)
            self.log(
                "Updating desktop entries (removing DXVK environment variables)...",
                "info",
            )
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            if not desktop_dir.exists():
                self.log("Desktop directory not found", "warning")
            else:
                affinity_desktop_files = [
                    desktop_dir / "AffinityPhoto.desktop",
                    desktop_dir / "AffinityDesigner.desktop",
                    desktop_dir / "AffinityPublisher.desktop",
                    desktop_dir / "Affinity.desktop",
                ]

                updated_count = 0
                for desktop_file in affinity_desktop_files:
                    if not desktop_file.exists():
                        continue

                    try:
                        # Read the desktop file
                        with open(desktop_file, "r") as f:
                            lines = f.readlines()

                        # Find and update the Exec line
                        new_lines = []
                        exec_updated = False

                        for line in lines:
                            if line.startswith("Exec="):
                                # Parse the existing Exec line
                                exec_content = line[5:].strip()

                                # Extract app path
                                quoted_path_match = re.search(
                                    r'wine\s+"([^"]+)"', exec_content
                                )
                                if quoted_path_match:
                                    app_path = quoted_path_match.group(1)
                                else:
                                    exe_match = re.search(
                                        r"wine\s+([^\s]+\.exe[^\s]*)", exec_content
                                    )
                                    if exe_match:
                                        app_path = exe_match.group(1)
                                    else:
                                        exe_match = re.search(
                                            r"([^\s]+\.exe[^\s]*)", exec_content
                                        )
                                        if exe_match:
                                            app_path = exe_match.group(1).strip('"')
                                        else:
                                            parts = exec_content.split()
                                            for part in reversed(parts):
                                                if ".exe" in part or "drive_c" in part:
                                                    app_path = part.strip('"')
                                                    break
                                            else:
                                                app_path = None

                                # Get wine path
                                wine = self.get_wine_path("wine")
                                wine_path = str(wine)

                                # Get GPU environment variables (but NOT DXVK)
                                gpu_env = self.get_gpu_env_vars()
                                directory_str = str(self.directory).rstrip("/")

                                # Rebuild Exec line WITHOUT DXVK env vars
                                exec_line = f"Exec=env WINEPREFIX={directory_str}"
                                if gpu_env:
                                    exec_line += f" {gpu_env}"
                                exec_line += f" {wine_path}"
                                if app_path:
                                    if " " in app_path or not app_path.startswith("/"):
                                        exec_line += f' "{app_path}"'
                                    else:
                                        exec_line += f" {app_path}"

                                new_lines.append(exec_line + "\n")
                                exec_updated = True
                            else:
                                new_lines.append(line)

                        # Write back if Exec line was updated
                        if exec_updated:
                            with open(desktop_file, "w") as f:
                                f.writelines(new_lines)
                            updated_count += 1
                            self.log(
                                f"Updated desktop entry: {desktop_file.name}", "success"
                            )

                    except Exception as e:
                        self.log(
                            f"Failed to update {desktop_file.name}: {e}", "warning"
                        )

                if updated_count > 0:
                    self.log(
                        f"Updated {updated_count} desktop entry/entries", "success"
                    )

            # Update button text
            self.update_switch_backend_button()

            self.show_message(
                "Switch to VKD3D Complete",
                f"Successfully switched to VKD3D!\n\n"
                f"• Installed vkd3d-proton with OpenCL support\n"
                f"• Installed d3d12.dll and d3d12core.dll\n"
                f"• Removed DXVK DLL overrides\n"
                f"• Set up DLL overrides for d3d12 and d3d12core in Wine registry\n"
                f"• Updated {updated_count} desktop entry/entries\n"
                f"• All Affinity applications will now use VKD3D with OpenCL support",
                "info",
            )

        except Exception as e:
            self.log(f"Error switching to VKD3D: {e}", "error")
            self.show_message(
                "Error", f"An error occurred while switching to VKD3D:\n\n{e}", "error"
            )

    def switch_to_dxvk(self):
        """Remove vkd3d and switch to DXVK using winetricks, updating all desktop entries"""
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Switch to DXVK",
            "This will:\n\n"
            "• Remove vkd3d-proton DLLs from Wine and application directories\n"
            "• Install DXVK via winetricks\n"
            "• Reinstall d3d12.dll and d3d12core.dll (required for compatibility)\n"
            "• Set preference to use DXVK instead\n"
            "• Update all desktop entries to use DXVK environment variables\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Switching to DXVK", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        try:
            # 0. Kill wineserver to avoid version mismatch issues
            self.log("Stopping wineserver to avoid version conflicts...", "info")
            wineserver = self.get_wine_path("wineserver")
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            self.run_command(
                [str(wineserver), "-k"], check=False, env=env, capture=True
            )
            import time

            time.sleep(1)  # Brief pause to ensure wineserver has stopped
            self.log("Wineserver stopped", "success")

            # 1. Remove vkd3d DLLs from Wine library directory
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            if wine_lib_dir.exists():
                self.log("Removing vkd3d DLLs from Wine library directory...", "info")
                for dll in ["d3d12.dll", "d3d12core.dll", "dxgi.dll"]:
                    dll_path = wine_lib_dir / dll
                    if dll_path.exists():
                        dll_path.unlink()
                        self.log(f"Removed {dll} from Wine library", "success")

                # Try to remove parent directories if empty
                try:
                    if wine_lib_dir.exists() and not any(wine_lib_dir.iterdir()):
                        wine_lib_dir.rmdir()
                    parent = wine_lib_dir.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    pass  # Ignore errors removing directories

            # 2. Remove vkd3d_dlls directory
            vkd3d_temp = Path(self.directory) / "vkd3d_dlls"
            if vkd3d_temp.exists():
                self.log("Removing vkd3d_dlls directory...", "info")
                try:
                    shutil.rmtree(vkd3d_temp)
                    self.log("Removed vkd3d_dlls directory", "success")
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove vkd3d_dlls directory: {e}",
                        "warning",
                    )

            # 3. Remove vkd3d DLLs from application directories
            app_dirs = {
                "Photo": "Photo 2",
                "Designer": "Designer 2",
                "Publisher": "Publisher 2",
                "Add": "Affinity",
            }

            for app_name, app_dir_name in app_dirs.items():
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / app_dir_name
                )
                if app_dir.exists():
                    for dll in ["d3d12.dll", "d3d12core.dll"]:
                        dll_path = app_dir / dll
                        if dll_path.exists():
                            dll_path.unlink()
                            self.log(f"Removed {dll} from {app_dir_name}", "success")

            # 4. Set preference to DXVK
            self.set_dxvk_vkd3d_preference("dxvk")
            self.log("Set preference to DXVK", "success")

            # 5. Remove vkd3d DLL overrides (if any)
            self.remove_d3d12_overrides()

            # 6. Install DXVK via winetricks
            self.log("Installing DXVK via winetricks...", "info")
            self.install_dxvk_dlls()

            # 7. Reinstall d3d12 DLLs and overrides (needed even with DXVK)
            self.log("Reinstalling d3d12 DLLs and setting up DLL overrides...", "info")
            self.install_d3d12_dlls()

            # 8. Copy DLLs back to application directories
            self.log("Copying d3d12 DLLs to application directories...", "info")
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            vkd3d_temp = Path(self.directory) / "vkd3d_dlls"

            for app_name, app_dir_name in app_dirs.items():
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / app_dir_name
                )
                if app_dir.exists():
                    for dll in ["d3d12.dll", "d3d12core.dll"]:
                        # Try wine library first, then temp directory
                        for source in [wine_lib_dir / dll, vkd3d_temp / dll]:
                            if source.exists():
                                shutil.copy2(source, app_dir / dll)
                                self.log(f"Copied {dll} to {app_dir_name}", "success")
                                break

            # 9. Update all desktop entries
            self.log(
                "Updating desktop entries with DXVK environment variables...", "info"
            )
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            if not desktop_dir.exists():
                self.log("Desktop directory not found", "warning")
            else:
                affinity_desktop_files = [
                    desktop_dir / "AffinityPhoto.desktop",
                    desktop_dir / "AffinityDesigner.desktop",
                    desktop_dir / "AffinityPublisher.desktop",
                    desktop_dir / "Affinity.desktop",
                ]

                updated_count = 0
                for desktop_file in affinity_desktop_files:
                    if not desktop_file.exists():
                        continue

                    try:
                        # Read the desktop file
                        with open(desktop_file, "r") as f:
                            lines = f.readlines()

                        # Find and update the Exec line
                        new_lines = []
                        exec_updated = False

                        for line in lines:
                            if line.startswith("Exec="):
                                # Parse the existing Exec line
                                exec_content = line[5:].strip()  # Remove "Exec=" prefix

                                # Extract app path
                                quoted_path_match = re.search(
                                    r'wine\s+"([^"]+)"', exec_content
                                )
                                if quoted_path_match:
                                    app_path = quoted_path_match.group(1)
                                else:
                                    exe_match = re.search(
                                        r"wine\s+([^\s]+\.exe[^\s]*)", exec_content
                                    )
                                    if exe_match:
                                        app_path = exe_match.group(1)
                                    else:
                                        exe_match = re.search(
                                            r"([^\s]+\.exe[^\s]*)", exec_content
                                        )
                                        if exe_match:
                                            app_path = exe_match.group(1).strip('"')
                                        else:
                                            parts = exec_content.split()
                                            for part in reversed(parts):
                                                if ".exe" in part or "drive_c" in part:
                                                    app_path = part.strip('"')
                                                    break
                                            else:
                                                app_path = None

                                # Get wine path
                                wine = self.get_wine_path("wine")
                                wine_path = str(wine)

                                # Get GPU and DXVK environment variables
                                gpu_env = self.get_gpu_env_vars()
                                dxvk_env = self.get_dxvk_env_vars()
                                directory_str = str(self.directory).rstrip("/")

                                # Rebuild Exec line with DXVK env vars
                                exec_line = f"Exec=env WINEPREFIX={directory_str}"
                                if gpu_env:
                                    exec_line += f" {gpu_env}"
                                if dxvk_env:
                                    exec_line += f" {dxvk_env}"
                                exec_line += f" {wine_path}"
                                if app_path:
                                    if " " in app_path or not app_path.startswith("/"):
                                        exec_line += f' "{app_path}"'
                                    else:
                                        exec_line += f" {app_path}"

                                new_lines.append(exec_line + "\n")
                                exec_updated = True
                            else:
                                new_lines.append(line)

                        # Write back if Exec line was updated
                        if exec_updated:
                            with open(desktop_file, "w") as f:
                                f.writelines(new_lines)
                            updated_count += 1
                            self.log(
                                f"Updated desktop entry: {desktop_file.name}", "success"
                            )

                    except Exception as e:
                        self.log(
                            f"Failed to update {desktop_file.name}: {e}", "warning"
                        )

                if updated_count > 0:
                    self.log(
                        f"Updated {updated_count} desktop entry/entries with DXVK configuration",
                        "success",
                    )

            # Update button text
            self.update_switch_backend_button()

            self.show_message(
                "Switch to DXVK Complete",
                f"Successfully switched to DXVK!\n\n"
                f"• Removed vkd3d-proton DLLs\n"
                f"• Removed vkd3d DLL overrides\n"
                f"• Installed DXVK via winetricks\n"
                f"• Reinstalled d3d12.dll and d3d12core.dll (required for compatibility)\n"
                f"• Updated {updated_count} desktop entry/entries\n"
                f"• All Affinity applications will now use DXVK for graphics acceleration",
                "info",
            )

        except Exception as e:
            self.log(f"Error switching to DXVK: {e}", "error")
            self.show_message(
                "Error", f"An error occurred while switching to DXVK:\n\n{e}", "error"
            )

    def update_existing_desktop_entries(self):
        """Update existing desktop entries with current GPU configuration"""
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        if not desktop_dir.exists():
            return

        # Get current GPU environment variables
        gpu_env = self.get_gpu_env_vars()
        # Get DXVK environment variables if AMD GPU is detected
        dxvk_env = self.get_dxvk_env_vars()
        directory_str = str(self.directory).rstrip("/")

        # Find all Affinity desktop entries
        affinity_desktop_files = [
            desktop_dir / "AffinityPhoto.desktop",
            desktop_dir / "AffinityDesigner.desktop",
            desktop_dir / "AffinityPublisher.desktop",
            desktop_dir / "Affinity.desktop",
        ]

        updated_count = 0
        for desktop_file in affinity_desktop_files:
            if not desktop_file.exists():
                continue

            try:
                # Read the desktop file
                with open(desktop_file, "r") as f:
                    lines = f.readlines()

                # Find and update the Exec line
                new_lines = []
                exec_updated = False

                for line in lines:
                    if line.startswith("Exec="):
                        # Parse the existing Exec line
                        exec_content = line[5:].strip()  # Remove "Exec=" prefix

                        # Use regex to extract the app path (everything after wine, typically in quotes or ending with .exe)
                        # Pattern 1: Find app path in quotes after wine
                        quoted_path_match = re.search(r'wine\s+"([^"]+)"', exec_content)
                        if quoted_path_match:
                            app_path = quoted_path_match.group(1)
                        else:
                            # Pattern 2: Find app path without quotes (look for .exe)
                            exe_match = re.search(
                                r"wine\s+([^\s]+\.exe[^\s]*)", exec_content
                            )
                            if exe_match:
                                app_path = exe_match.group(1)
                            else:
                                # Pattern 3: Find any path containing .exe
                                exe_match = re.search(
                                    r"([^\s]+\.exe[^\s]*)", exec_content
                                )
                                if exe_match:
                                    app_path = exe_match.group(1).strip('"')
                                else:
                                    # Fallback: try to extract from the end
                                    parts = exec_content.split()
                                    for part in reversed(parts):
                                        if ".exe" in part or "drive_c" in part:
                                            app_path = part.strip('"')
                                            break

                        # Get wine path (standard location)
                        wine = self.get_wine_path("wine")
                        wine_path = str(wine)

                        # Rebuild Exec line with new GPU env vars
                        exec_line = f"Exec=env WINEPREFIX={directory_str}"
                        if gpu_env:
                            exec_line += f" {gpu_env}"
                        if dxvk_env:
                            exec_line += f" {dxvk_env}"
                        exec_line += f" {wine_path}"
                        if app_path:
                            # Quote the app path if it contains spaces or special characters
                            if " " in app_path or not app_path.startswith("/"):
                                exec_line += f' "{app_path}"'
                            else:
                                exec_line += f" {app_path}"
                        else:
                            # If we couldn't parse app_path, log a warning but still update GPU env
                            self.log(
                                f"Warning: Could not parse app path from {desktop_file.name}, updating GPU env only",
                                "warning",
                            )

                        new_lines.append(exec_line + "\n")
                        exec_updated = True
                    else:
                        new_lines.append(line)

                # Write back if Exec line was updated
                if exec_updated:
                    with open(desktop_file, "w") as f:
                        f.writelines(new_lines)
                    updated_count += 1
                    self.log(f"Updated desktop entry: {desktop_file.name}", "info")

            except Exception as e:
                self.log(f"Failed to update {desktop_file.name}: {e}", "warning")

        if updated_count > 0:
            self.log(
                f"Updated {updated_count} desktop entry/entries with new GPU configuration",
                "success",
            )
        else:
            self.log("No desktop entries found to update", "info")

    def format_distro_name(self, distro=None):
        """Format distribution name for display with proper capitalization"""
        if distro is None:
            distro = self.distro

        # Map lowercase distro IDs to proper display names
        distro_names = {
            "arch": "Arch",
            "cachyos": "CachyOS",
            "endeavouros": "EndeavourOS",
            "xerolinux": "XeroLinux",
            "fedora": "Fedora",
            "nobara": "Nobara",
            "opensuse-tumbleweed": "openSUSE Tumbleweed",
            "opensuse-leap": "openSUSE Leap",
            "pikaos": "PikaOS",
            "pop": "Pop!_OS",
            "ubuntu": "Ubuntu",
            "linuxmint": "Linux Mint",
            "zorin": "Zorin OS",
            "debian": "Debian",
            "manjaro": "Manjaro",
        }

        return distro_names.get(
            distro.lower() if distro else "", distro.title() if distro else "Unknown"
        )

    def download_file(self, url, output_path, description=""):
        """Download file with progress tracking"""
        try:
            # Check if cancelled before starting
            if self.check_cancelled():
                return False

            self.log(f"Downloading {description}...", "info")

            # Create request with proper headers
            req = urllib.request.Request(url)
            req.add_header(
                "User-Agent",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            )
            req.add_header("Accept", "*/*")

            # Use urlopen for better header support and manual progress tracking
            with urllib.request.urlopen(req) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                block_size = 8192

                with open(output_path, "wb") as out_file:
                    while True:
                        # Check for cancellation during download
                        if self.check_cancelled():
                            self.log(f"Download of {description} cancelled", "warning")
                            return False

                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = min(100, (downloaded * 100) // total_size)
                            self.update_progress(percent / 100.0)

                self.update_progress(1.0)
                return True
        except urllib.error.HTTPError as e:
            self.log(f"Download failed: HTTP {e.code} {e.reason}", "error")
            if e.code == 404:
                self.log(f"  URL may be expired or invalid: {url[:80]}...", "warning")
            return False
        except Exception as e:
            self.log(f"Download failed: {e}", "error")
            return False

    def start_initialization(self):
        """Start initialization process"""
        threading.Thread(target=self.initialize, daemon=True).start()

    def initialize(self):
        """Initialize installer"""
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Affinity Linux Installer - Initialization", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Detect distribution
        self.update_progress(0.1)
        if not self.detect_distro():
            self.log("Failed to detect distribution. Exiting.", "error")
            return

        self.log(
            f"Detected distribution: {self.format_distro_name()} {self.distro_version or ''}",
            "success",
        )
        self.update_progress(0.2)

        # Check dependencies
        if not self.check_dependencies():
            return

        # Check if Wine is already set up
        wine = self.get_wine_path("wine")
        if wine.exists():
            self.log("Wine is already set up", "success")
        else:
            self.log(
                "Wine is not set up. Use 'Setup Wine Environment' to install it.",
                "info",
            )

        # Show main menu (Wine setup can be done manually if needed)
        self.update_progress(1.0)
        QTimer.singleShot(0, self.show_main_menu)

    def one_click_setup(self):
        """One-click full setup: detects distro, installs deps, sets up Wine, installs Winetricks deps"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("One-Click Full Setup", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log("This will automatically:", "info")
        self.log("  1. Detect your Linux distribution", "info")
        self.log("  2. Check and install system dependencies", "info")
        self.log("  3. Setup Wine environment (download and configure)", "info")
        self.log("  4. Install Winetricks dependencies (.NET, fonts, etc.)", "info")
        self.log("  5. Prompt you to install an Affinity application\n", "info")

        threading.Thread(target=self._one_click_setup_thread, daemon=True).start()

    def _one_click_setup_thread(self):
        """One-click setup in background thread"""
        self.start_operation("One-Click Full Setup")

        # Ensure patcher files are available
        self.ensure_patcher_files()

        # Ask which GPU to use (for multi GPUs systems)
        gpus = self.detect_gpus()
        gpu_config_file = Path(self.directory) / ".gpu_config"
        if not gpu_config_file.exists() and len(gpus) > 2:
            self.configure_gpu_selection()

        if self.check_cancelled():
            return

        # Ask about OpenCL support (only if not already configured)
        opencl_config_file = Path(self.directory) / ".opencl_enabled"
        if not opencl_config_file.exists():
            opencl_reply = self.show_question_dialog(
                "Enable OpenCL Support?",
                "OpenCL (Open Computing Language) enables hardware acceleration for certain features in Affinity applications, "
                "which can improve performance for tasks like image processing, filters, and effects.\n\n"
                "This will download and configure vkd3d-proton, which provides OpenCL support through Vulkan.\n\n"
                "Would you like to enable OpenCL support?\n\n"
                "Note: You can change this setting later if needed.",
                ["Yes", "No"],
            )

            if opencl_reply == "Yes":
                self.enable_opencl = True
                self.log("OpenCL support will be enabled", "info")

                # Check if AMD GPU is detected and install additional dependencies based on distribution
                if self.has_amd_gpu():
                    self.log(
                        "AMD GPU detected - installing additional OpenCL dependencies...",
                        "info",
                    )

                    amd_deps = []
                    install_cmd = None

                    # Fedora
                    if self.distro == "fedora":
                        # Check if Fedora 43 - use different dependencies
                        if self.distro_version == "43":
                            amd_deps = [
                                "mesa-opencl-icd",
                                "ocl-icd",
                                "rocm-opencl",
                                "rocm-hip",
                                "wine-opencl",
                            ]
                            self.log(
                                "Fedora 43 detected - installing Fedora 43 specific AMD OpenCL dependencies...",
                                "info",
                            )
                        else:
                            # Use older dependencies for other Fedora versions
                            amd_deps = [
                                "rocm-opencl",
                                "apr",
                                "apr-util",
                                "zlib",
                                "libxcrypt-compat",
                                "libcurl",
                                "libcurl-devel",
                                "mesa-libGLU",
                            ]
                        install_cmd = ["sudo", "dnf", "install", "-y"] + amd_deps

                    # Arch-based distributions (Arch, Artix, CachyOS, EndeavourOS, XeroLinux)
                    elif self.distro in ["arch", "artix", "cachyos", "endeavouros", "xerolinux"]:
                        # Arch uses different package names than Fedora
                        amd_deps = [
                            "opencl-mesa",
                            "ocl-icd",
                            "rocm-opencl-runtime",
                            "rocm-hip",
                            "wine-opencl",
                        ]
                        self.log(
                            f"{self.format_distro_name()} detected - installing Arch-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = [
                            "sudo",
                            "pacman",
                            "-S",
                            "--needed",
                            "--noconfirm",
                        ] + amd_deps

                    # PikaOS (Ubuntu/Debian-based)
                    elif self.distro == "pikaos":
                        # PikaOS uses Debian/Ubuntu package names
                        amd_deps = [
                            "mesa-opencl-icd",
                            "ocl-icd-libopencl1",
                            "rocm-opencl-runtime",
                            "rocm-hip-runtime",
                        ]
                        self.log(
                            "PikaOS detected - installing Debian/Ubuntu-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = ["sudo", "apt", "install", "-y"] + amd_deps

                    # Install dependencies if we have a command
                    if install_cmd and amd_deps:
                        self.log(f"Installing: {', '.join(amd_deps)}", "info")
                        success, stdout, stderr = self.run_command(install_cmd)

                        if success:
                            self.log(
                                "AMD OpenCL dependencies installed successfully",
                                "success",
                            )
                        else:
                            self.log(
                                f"Warning: Failed to install some AMD OpenCL dependencies: {stderr}",
                                "warning",
                            )
                            self.log(
                                "OpenCL may still work, but some features might be limited",
                                "warning",
                            )
            else:
                self.enable_opencl = False
                self.log("OpenCL support will be disabled", "info")

            # Save OpenCL preference
            try:
                with open(opencl_config_file, "w") as f:
                    f.write("1" if self.enable_opencl else "0")
            except Exception as e:
                self.log(f"Failed to save OpenCL preference: {e}", "warning")
        else:
            # Load existing preference
            self.enable_opencl = self.is_opencl_enabled()
            if self.enable_opencl:
                self.log("OpenCL support is enabled (from previous setup)", "info")
            else:
                self.log("OpenCL support is disabled (from previous setup)", "info")

        if self.check_cancelled():
            return

        # Step 1: Detect distribution
        self.update_progress_text("Step 1/4: Detecting Linux distribution...")
        self.update_progress(0.05)

        if self.check_cancelled():
            return

        if not self.detect_distro():
            self.log("Failed to detect distribution. Cannot continue.", "error")
            self.update_progress_text("Ready")
            self.end_operation()
            return

        self.log(
            f"Detected distribution: {self.format_distro_name()} {self.distro_version or ''}",
            "success",
        )

        if self.check_cancelled():
            return

        # Step 2: Check and install dependencies
        self.update_progress_text(
            "Step 2/4: Checking and installing system dependencies..."
        )
        self.update_progress(0.15)

        if self.check_cancelled():
            return

        if not self.check_dependencies():
            self.log(
                "Dependency check failed. Please resolve issues and try again.", "error"
            )
            self.update_progress_text("Ready")
            self.end_operation()

            # Show retry dialog
            reply = self.show_question_dialog(
                "Dependency Check Failed",
                "Dependency check failed. Please resolve issues and try again.\n\n"
                "Would you like to retry the dependency check?",
                ["Yes", "No"],
            )

            if reply == "Yes":
                # Retry dependency check
                return self._one_click_setup_thread()
            else:
                self.end_operation()
                return

        if self.check_cancelled():
            return

        # Step 3: Setup Wine environment (this includes winetricks dependencies via configure_wine)
        self.update_progress_text("Step 3/4: Setting up Wine environment...")
        self.update_progress(0.40)

        if self.check_cancelled():
            return

        # Ask user to choose Wine version
        wine_version = self.show_question_dialog(
            "Choose Wine Version",
            "Which Wine version would you like to install?\n\n"
            "• Wine 11.0 (Recommended) - ElementalWarrior Wine 11.0 with AMD GPU and OpenCL patches. Latest version with best compatibility and performance.\n"
            "• Wine 10.10 - ElementalWarrior Wine 10.10 with AMD GPU and OpenCL patches. Previous stable version.\n"
            "• Wine 9.14 (Legacy) - Legacy version with AMD GPU and OpenCL patches. Fallback option if you encounter issues with newer versions.\n\n"
            "Note: You can switch versions later by running 'Setup Wine Environment' again.",
            ["Wine 11.0 (Recommended)", "Wine 10.10", "Wine 9.14 (Legacy)"],
        )

        if wine_version == "Wine 11.0 (Recommended)":
            wine_version_choice = "11.0"
        elif wine_version == "Wine 10.10":
            wine_version_choice = "10.10"
        elif wine_version == "Wine 9.14 (Legacy)":
            wine_version_choice = "9.14"
        else:
            self.log("Wine setup cancelled", "warning")
            return

        self.setup_wine(wine_version_choice)

        if self.check_cancelled():
            return

        # Step 4: Install Affinity v3 settings to enable settings saving
        self.update_progress_text("Step 4/5: Installing Affinity v3 settings...")
        self.update_progress(0.80)

        if self.check_cancelled():
            return

        self.log("Installing Affinity v3 settings files...", "info")
        self._install_affinity_settings_thread()

        if self.check_cancelled():
            return

        # Step 5: Install AffinityPluginLoader + WineFix
        self.update_progress_text(
            "Step 5/5: Installing AffinityPluginLoader + WineFix..."
        )
        self.update_progress(0.90)

        if self.check_cancelled():
            return

        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        if install_dir.exists():
            self.log("\nInstalling AffinityPluginLoader + WineFix...", "info")
            self._install_affinity_plugin_loader_thread(standalone=False)
        else:
            self.log(
                "\nSkipping AffinityPluginLoader install - Affinity not yet installed.",
                "info",
            )
            self.log(
                "Use the 'Install AffinityPluginLoader' button after installing Affinity.",
                "info",
            )

        if self.check_cancelled():
            return

        # Complete!
        self.update_progress(1.0)
        self.update_progress_text("Setup Complete!")
        self.log("\n✓ Full setup completed!", "success")
        self.log(
            "You can now install Affinity applications using the buttons above.", "info"
        )

        # End operation
        self.end_operation()

        # Refresh installation status to update button states
        QTimer.singleShot(100, self.check_installation_status)

        # Ask if user wants to install an Affinity app
        self.prompt_affinity_install_signal.emit()

    def _prompt_affinity_install(self):
        """Prompt user to install an Affinity application"""
        reply = QMessageBox.question(
            self,
            "Install Affinity Application",
            "Setup is complete!\n\nWould you like to install an Affinity application now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Show a dialog to select which app (without parent to avoid threading issues)
            dialog = QDialog()
            dialog.setWindowTitle("Select Affinity Application")
            dialog.setModal(True)
            dialog.setWindowFlags(
                dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
            )

            # Responsive sizing
            screen = dialog.screen().availableGeometry()
            screen_width = screen.width()
            screen_height = screen.height()

            if screen_width < 800 or screen_height < 600:
                min_width = min(400, int(screen_width * 0.9))
                min_height = min(300, int(screen_height * 0.7))
                default_width = min(500, int(screen_width * 0.85))
                default_height = min(350, int(screen_height * 0.65))
                max_width = int(screen_width * 0.95)
                max_height = int(screen_height * 0.85)
            elif screen_width < 1280 or screen_height < 720:
                min_width = 450
                min_height = 320
                default_width = 550
                default_height = 380
                max_width = int(screen_width * 0.9)
                max_height = int(screen_height * 0.85)
            else:
                min_width = 450
                min_height = 320
                default_width = 550
                default_height = 380
                max_width = 800
                max_height = 700

            dialog.setMinimumWidth(min_width)
            dialog.setMinimumHeight(min_height)
            dialog.setMaximumWidth(max_width)
            dialog.setMaximumHeight(max_height)
            dialog.resize(default_width, default_height)
            dialog.setSizeGripEnabled(True)
            dialog.setStyleSheet(self.get_dialog_stylesheet())

            # Main layout
            main_layout = QVBoxLayout(dialog)
            main_layout.setSpacing(12)
            margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
            main_layout.setContentsMargins(margin, margin, margin, margin)

            # Title
            title_label = QLabel("Select Affinity Application")
            title_label.setObjectName("titleLabel")
            title_label.setWordWrap(True)
            title_label.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
            )
            main_layout.addWidget(title_label)

            # Description
            desc_label = QLabel("Which Affinity application would you like to install?")
            desc_label.setObjectName("descriptionLabel")
            desc_label.setWordWrap(True)
            desc_label.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
            )
            main_layout.addWidget(desc_label)

            # Options container with scroll area for better scaling
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            scroll_area.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

            options_container = QFrame()
            options_container.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
            )
            options_layout = QVBoxLayout(options_container)
            options_layout.setSpacing(8)
            options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
            options_layout.setContentsMargins(
                options_margin, options_margin, options_margin, options_margin
            )

            scroll_area.setWidget(options_container)

            button_group = QButtonGroup()
            apps = [
                ("Add", "Affinity (Unified)"),
                ("Photo", "Affinity Photo"),
                ("Designer", "Affinity Designer"),
                ("Publisher", "Affinity Publisher"),
            ]

            radio_buttons = {}
            for idx, (app_code, app_name) in enumerate(apps):
                app_frame = QFrame()
                app_frame.setObjectName("optionFrame")
                app_layout = QVBoxLayout(app_frame)
                app_layout.setContentsMargins(12, 10, 12, 10)
                radio = QRadioButton(app_name)
                if app_code == "Add":
                    radio.setChecked(True)
                radio.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
                )
                app_layout.addWidget(radio)
                options_layout.addWidget(app_frame)
                button_group.addButton(radio, idx)
                radio_buttons[idx] = app_code

            main_layout.addWidget(scroll_area, 1)

            # Buttons
            button_layout = QHBoxLayout()
            button_layout.setSpacing(10)
            button_layout.addStretch()

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
            )
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)

            ok_btn = QPushButton("Continue")
            ok_btn.setObjectName("okButton")
            ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            ok_btn.setDefault(True)
            ok_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(ok_btn)

            main_layout.addLayout(button_layout)

            # Show dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

            if dialog.exec() == QDialog.DialogCode.Accepted:
                checked_id = button_group.checkedId()
                if checked_id >= 0 and checked_id in radio_buttons:
                    app_code = radio_buttons[checked_id]
                    self.install_application_signal.emit(app_code)

    def install_application(self, app_code):
        """Install an Affinity application - asks user if they want to download or provide their own exe"""
        app_names = {
            "Add": "Affinity (Unified)",
            "Photo": "Affinity Photo",
            "Designer": "Affinity Designer",
            "Publisher": "Affinity Publisher",
        }
        display_name = app_names.get(app_code, "Affinity")

        # Check if Wine is set up
        wine = self.get_wine_path("wine")
        if not wine.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # Ask user if they want to download or provide their own exe (without parent to avoid threading issues)
        dialog = QDialog()
        dialog.setWindowTitle(f"Install {display_name}")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(280, int(screen_height * 0.7))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(320, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 450
            min_height = 300
            default_width = 550
            default_height = 350
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 450
            min_height = 300
            default_width = 550
            default_height = 350
            max_width = 800
            max_height = 600

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel(f"Install {display_name}")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(f"How would you like to get the {display_name} installer?")
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        button_group = QButtonGroup()

        # Download option
        download_frame = QFrame()
        download_frame.setObjectName("optionFrame")
        download_layout = QVBoxLayout(download_frame)
        download_layout.setContentsMargins(12, 10, 12, 10)
        download_radio = QRadioButton("Download from Affinity Studio (automatic)")
        download_radio.setChecked(True)
        download_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        download_layout.addWidget(download_radio)
        options_layout.addWidget(download_frame)
        button_group.addButton(download_radio, 0)

        # Custom option
        custom_frame = QFrame()
        custom_frame.setObjectName("optionFrame")
        custom_layout = QVBoxLayout(custom_frame)
        custom_layout.setContentsMargins(12, 10, 12, 10)
        custom_radio = QRadioButton("Provide my own installer file (.exe)")
        custom_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        custom_layout.addWidget(custom_radio)
        options_layout.addWidget(custom_frame)
        button_group.addButton(custom_radio, 1)

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            checked_id = button_group.checkedId()
            installer_path = None

            if checked_id == 0:  # Download
                # Download the installer in background, then install
                self.log(
                    f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log(f"Downloading {display_name} Installer", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )

                download_url = "https://downloads.affinity.studio/Affinity%20x64.exe"
                # Download to .AffinityLinux/Installer/ directory
                download_dir = Path(self.directory) / "Installer"
                download_dir.mkdir(parents=True, exist_ok=True)
                installer_path = download_dir / "Affinity-x64.exe"
                self.log(f"Downloading to: {installer_path}", "info")

                self.start_operation(f"Install {display_name}")
                threading.Thread(
                    target=self._download_then_install,
                    args=(app_code, display_name, download_url, str(installer_path)),
                    daemon=True,
                ).start()
                return

            else:  # Provide own file
                # Open file dialog to select .exe
                self.log(
                    f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log(f"Custom Installer for {display_name}", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self.log("Please select the installer .exe file...", "info")

                installer_path, _ = QFileDialog.getOpenFileName(
                    self,
                    f"Select {display_name} Installer",
                    "",
                    "Executable files (*.exe);;All files (*.*)",
                )

                if not installer_path:
                    self.log("Installation cancelled.", "warning")
                    return
                # QFileDialog returns a string, but we'll normalize it
                installer_path = Path(installer_path)

            # Verify file exists and convert to string for run_installation
            installer_path_str = str(installer_path)
            if not Path(installer_path_str).exists():
                self.log(f"Installer file not found: {installer_path_str}", "error")
                return

            # Start operation and installation in background thread
            self.start_operation(f"Install {display_name}")
            threading.Thread(
                target=self._run_installation_entry,
                args=(app_code, installer_path_str),
                daemon=True,
            ).start()

    def _download_then_install(
        self, app_code, display_name, download_url, installer_path_str
    ):
        """Download installer then run installation (runs in background)."""
        try:
            self.log(f"Downloading from: {download_url}", "info")
            if not self.download_file(
                download_url, installer_path_str, f"{display_name} installer"
            ):
                self.log(
                    "Download failed. Please try providing your own installer file.",
                    "error",
                )
                self.show_message(
                    "Download Failed",
                    "Failed to download the installer.\n\nYou can download it manually from:\nhttps://downloads.affinity.studio/Affinity%20x64.exe\n\nThen use 'Provide my own installer file' option.",
                    "error",
                )
                # End the operation because run_installation won't be called
                self.end_operation()
                return
            self.log(f"Download completed: {installer_path_str}", "success")
            # Proceed to install (will end operation in wrapper)
            self._run_installation_entry(app_code, installer_path_str)
        except Exception as e:
            self.log(f"Error during download+install: {e}", "error")
            self.end_operation()

    def check_dependencies(self):
        """Check and install dependencies"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Dependency Verification", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        self.update_progress_text("Checking dependencies...")
        self.update_progress(0.0)

        # Show unsupported warning
        if self.distro in ["bazzite"]:
            self.show_unsupported_warning()

        missing = []
        deps = ["wine", "winetricks", "wget", "curl", "tar", "jq"]
        total_checks = len(deps) + 3  # +3 for archive tools, zstd, and dotnet

        for idx, dep in enumerate(deps):
            progress = (idx + 1) / total_checks * 0.5  # Use first 50% for checking
            self.update_progress(progress)
            self.update_progress_text(f"Checking {dep}...")

            if self.check_command(dep):
                self.log(f"{dep} is installed", "success")
            else:
                self.log(f"{dep} is not installed", "error")
                missing.append(dep)

        # Check for either 7z or unzip (both can extract archives)
        progress = (len(deps) + 1) / total_checks * 0.5
        self.update_progress(progress)
        self.update_progress_text("Checking archive tools...")

        if not self.check_command("7z") and not self.check_command("unzip"):
            self.log(
                "Neither 7z nor unzip is installed (at least one is required)", "error"
            )
            missing.append("7z or unzip")
        else:
            if self.check_command("7z"):
                self.log("7z is installed", "success")
            else:
                self.log("unzip is installed (will be used instead of 7z)", "success")

        # Check zstd
        progress = (len(deps) + 2) / total_checks * 0.5
        self.update_progress(progress)
        self.update_progress_text("Checking zstd...")

        if not (self.check_command("unzstd") or self.check_command("zstd")):
            self.log("zstd or unzstd is not installed", "error")
            missing.append("zstd")
        else:
            self.log("zstd support is available", "success")

        # Check .NET SDK (optional but recommended for Affinity v3 settings fix)
        progress = (len(deps) + 3) / total_checks * 0.5
        self.update_progress(progress)
        self.update_progress_text("Checking .NET SDK...")

        if not self.check_dotnet_sdk():
            self.log(
                ".NET SDK is not installed (optional - needed for Affinity v3 settings fix)",
                "warning",
            )
            missing.append("dotnet-sdk")
        else:
            self.log(".NET SDK is installed", "success")

        # Handle unsupported distributions - show warning and allow retry
        if self.distro in ["bazzite"]:
            if missing:
                self.log("\n" + "=" * 80, "error")
                self.log("⚠️  WARNING: UNSUPPORTED DISTRIBUTION", "error")
                self.log("=" * 80, "error")
                self.log("\nMissing dependencies detected.", "error")
                self.log(
                    "This script will NOT auto-install for unsupported distributions.",
                    "error",
                )
                self.log(
                    "Please install the required dependencies manually.", "warning"
                )
                self.log(f"Missing: {', '.join(missing)}", "warning")

                # Show dialog asking user to install and retry
                reply = self.show_question_dialog(
                    "Unsupported Distribution - Missing Dependencies",
                    f"⚠️  WARNING: UNSUPPORTED DISTRIBUTION\n\n"
                    f"Missing dependencies: {', '.join(missing)}\n\n"
                    f"This script will NOT auto-install for unsupported distributions.\n"
                    f"Please install the required dependencies manually.\n\n"
                    f"Click 'Retry' after installing dependencies, or 'Cancel' to exit.",
                    ["Retry", "Cancel"],
                )

                if reply == "Retry":
                    # Re-check dependencies
                    return self.check_dependencies()
                else:
                    return False
            else:
                self.log(
                    "\nAll dependencies installed, but you are on an unsupported distribution.",
                    "warning",
                )
                self.log("No support will be provided if issues arise.", "warning")

        # Install missing dependencies (only for supported distributions)
        # For Ubuntu/Mint/Zorin, always run WineHQ setup to ensure proper Wine version
        if self.distro in ["ubuntu", "linuxmint", "zorin"]:
            # Always run WineHQ setup for Ubuntu-based distros
            self.log(f"\nSetting up WineHQ for {self.format_distro_name()}...", "info")
            self.update_progress_text(
                f"Setting up Wine for {self.format_distro_name()}..."
            )

            # Request password before attempting installation
            self.log(
                "Administrator privileges required for package installation.", "info"
            )
            self.update_progress_text("Requesting administrator password...")

            password = self.get_sudo_password()
            if password is None:
                self.log(
                    "Password entry cancelled. Cannot install dependencies.", "error"
                )
                return False

            if not self.sudo_password_validated:
                if not self.validate_sudo_password(password):
                    self.log(
                        "Password validation failed. Cannot install dependencies.",
                        "error",
                    )
                    return False

            return self.install_dependencies()
        elif missing and self.distro not in ["bazzite"]:
            self.log(f"\nInstalling missing dependencies: {', '.join(missing)}", "info")
            self.update_progress_text(f"Installing {len(missing)} missing packages...")
            self.update_progress(0.5)  # Start second half of progress

            # Request password before attempting installation
            self.log(
                "Administrator privileges required for package installation.", "info"
            )
            self.update_progress_text("Requesting administrator password...")

            # Try to get and validate password (with retries)
            max_password_attempts = 3
            password_valid = False

            for password_attempt in range(max_password_attempts):
                password = self.get_sudo_password()
                if password is None:
                    self.log(
                        "Password entry cancelled. Cannot install dependencies.",
                        "error",
                    )
                    self.update_progress_text("Dependency installation cancelled")
                    return False

                # Validate password before proceeding
                if not self.sudo_password_validated:
                    self.log(
                        f"Validating password... (attempt {password_attempt + 1}/{max_password_attempts})",
                        "info",
                    )
                    if self.validate_sudo_password(password):
                        self.log("Password validated successfully.", "success")
                        password_valid = True
                        break
                    else:
                        if password_attempt < max_password_attempts - 1:
                            self.log(
                                "Password validation failed. Please try again.", "error"
                            )
                            # Clear the password to force a new dialog on next get_sudo_password call
                            self.sudo_password = None
                            self.sudo_password_validated = False
                            # Wait a moment for user to see the error message
                            time.sleep(1)
                        else:
                            self.log(
                                "Password validation failed after multiple attempts.",
                                "error",
                            )
                            return False
                else:
                    # Password already validated
                    password_valid = True
                    break

            if not password_valid:
                self.log(
                    "Could not validate password. Cannot install dependencies.", "error"
                )
                self.update_progress_text("Dependency installation cancelled")
                return False

            if not self.install_dependencies():
                self.update_progress_text("Dependency installation failed")
                return False

        self.update_progress(1.0)
        self.update_progress_text("All dependencies installed")
        self.log("\n✓ All required dependencies are installed!", "success")
        return True

    def show_unsupported_warning(self):
        """Display unsupported distribution warning"""
        self.log("\n" + "=" * 80, "warning")
        self.log("⚠️  WARNING: UNSUPPORTED DISTRIBUTION", "error")
        self.log("=" * 80, "warning")
        self.log(f"\nYOU ARE ON YOUR OWN!", "error")
        self.log(
            f"\nThe distribution ({self.format_distro_name()}) is OUT OF DATE",
            "warning",
        )
        self.log("and the script will NOT be built around it.", "warning")
        self.log("\nFor a modern, stable Linux experience, please consider:", "info")
        self.log("  • PikaOS 4", "success")
        self.log("  • CachyOS", "success")
        self.log("  • Nobara", "success")
        self.log("=" * 80 + "\n", "warning")

    def install_dependencies(self):
        """Install dependencies based on distribution"""
        self.log(
            f"DEBUG: install_dependencies called with distro={self.distro}", "info"
        )
        if self.distro == "pikaos":
            return self.install_pikaos_dependencies()
        if self.distro == "pop":
            return self.install_popos_dependencies()
        if self.distro in ["ubuntu", "linuxmint", "zorin"]:
            return self.install_ubuntu_based_dependencies()

        commands = {
            "arch": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "artix": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "cachyos": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "endeavouros": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "xerolinux": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "manjaro": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "fedora": [
                "sudo",
                "dnf",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "p7zip-plugins",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "nobara": [
                "sudo",
                "dnf",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "p7zip-plugins",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "opensuse-tumbleweed": [
                "sudo",
                "zypper",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "opensuse-leap": [
                "sudo",
                "zypper",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
        }

        if self.distro in commands:
            self.log(
                f"Installing dependencies for {self.format_distro_name()}...", "info"
            )
            self.update_progress_text(
                f"Installing packages for {self.format_distro_name()}..."
            )
            self.update_progress(0.6)

            success, stdout, stderr = self.run_command(commands[self.distro])

            if success:
                self.update_progress(1.0)
                self.update_progress_text("Dependencies installed")
                self.log("Dependencies installed successfully", "success")
                return True
            else:
                self.log(f"Failed to install dependencies: {stderr}", "error")

                # Show retry dialog
                reply = self.show_question_dialog(
                    "Dependency Installation Failed",
                    f"Failed to install dependencies:\n{stderr}\n\n"
                    "Would you like to retry the installation?",
                    ["Yes", "No"],
                )

                if reply == "Yes":
                    # Retry installation
                    return self.install_dependencies()
                else:
                    return False

        self.log(f"Unsupported distribution: {self.format_distro_name()}", "error")
        return False

    def install_pikaos_dependencies(self):
        """Install PikaOS dependencies with WineHQ staging"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("PikaOS Special Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log("PikaOS's built-in Wine has compatibility issues.", "warning")
        self.log("Setting up WineHQ staging from Debian...\n", "info")

        # Total steps: keyrings, gpg key, i386, repo, apt update, wine install, deps install, winetricks install = 8 steps
        total_steps = 8
        current_step = 0

        # Create keyrings directory
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Creating keyrings directory..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Creating APT keyrings directory...", "info")
        success, _, _ = self.run_command(
            ["sudo", "mkdir", "-pm755", "/etc/apt/keyrings"]
        )
        if not success:
            self.log("Failed to create keyrings directory", "error")
            return False

        # Add GPG key
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ GPG key..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ GPG key...", "info")

        # Get sudo password for GPG operation
        password = self.get_sudo_password()
        if password is None:
            self.log("Authentication cancelled by user", "error")
            return False

        # Validate password if not already validated
        if not self.sudo_password_validated:
            if not self.validate_sudo_password(password):
                self.log("Authentication failed", "error")
                return False

        # Download GPG key to temporary file first (handles binary data correctly)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_key_path = tmp_file.name

        try:
            # Download the key in binary mode
            success, _, _ = self.run_command(
                [
                    "wget",
                    "-O",
                    tmp_key_path,
                    "https://dl.winehq.org/wine-builds/winehq.key",
                ]
            )
            if not success:
                self.log("Failed to download GPG key", "error")
                os.unlink(tmp_key_path)
                return False

            # Read the key file in binary mode
            with open(tmp_key_path, "rb") as key_file:
                key_data = key_file.read()

            # Clean up temp file
            os.unlink(tmp_key_path)

            # Run GPG command with sudo, passing binary key data
            gpg_proc = subprocess.Popen(
                [
                    "sudo",
                    "-S",
                    "gpg",
                    "--dearmor",
                    "-o",
                    "/etc/apt/keyrings/winehq-archive.key",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Send password first (as bytes), then the key data (binary)
            gpg_input = f"{self.sudo_password}\n".encode() + key_data
            gpg_stdout, gpg_stderr = gpg_proc.communicate(input=gpg_input)

            if gpg_proc.returncode == 0:
                self.log("WineHQ GPG key added", "success")
            else:
                error_msg = (
                    gpg_stderr.decode("utf-8", errors="ignore")
                    if gpg_stderr
                    else "Unknown error"
                )
                self.log(f"Failed to add GPG key: {error_msg}", "error")
                return False
        except Exception as e:
            # Clean up temp file on error
            import os as _os

            if _os.path.exists(tmp_key_path):
                try:
                    _os.unlink(tmp_key_path)
                except:
                    pass
            self.log(f"Failed to add GPG key: {str(e)}", "error")
            return False

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, _, _ = self.run_command(["sudo", "dpkg", "--add-architecture", "i386"])
        if not success:
            self.log("Failed to add i386 architecture", "error")
            return False

        # Add repository
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ repository..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ repository...", "info")

        # Always use Debian testing repository for the newest WineHQ packages
        # This ensures we get the latest WineHQ versions without needing to update
        # the script every Debian release. Debian testing codename is currently "forky"
        codename = "forky"  # Debian testing
        self.log(
            f"Using Debian testing (forky) repository for latest WineHQ packages",
            "info",
        )

        # Remove existing WineHQ repository files first to avoid conflicts
        repo_pattern = Path("/etc/apt/sources.list.d/")
        for repo_file in repo_pattern.glob("winehq-*.sources"):
            self.run_command(["sudo", "rm", "-f", str(repo_file)], check=False)

        # Add the repository using the detected codename
        # Use -NP flags: -N for timestamping, -P for directory
        success, _, _ = self.run_command(
            [
                "sudo",
                "wget",
                "-NP",
                "/etc/apt/sources.list.d/",
                f"https://dl.winehq.org/wine-builds/debian/dists/{codename}/winehq-{codename}.sources",
            ]
        )
        if not success:
            self.log(f"Failed to add repository for {codename}", "error")
            return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install WineHQ staging
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing WineHQ staging..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing WineHQ staging...", "info")
        success, _, _ = self.run_command(
            ["sudo", "apt", "install", "--install-recommends", "-y", "winehq-staging"]
        )
        if not success:
            self.log("Failed to install WineHQ staging", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "wget",
                "curl",
                "p7zip-full",
                "tar",
                "jq",
                "zstd",
            ]
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            return False

        # Install winetricks from source
        self.log("Installing winetricks from source...", "info")
        success, _, _ = self.run_command(
            ["git", "clone", "https://github.com/Winetricks/winetricks"]
        )
        if not success:
            self.log("Failed to clone winetricks repository", "error")
            return False

        # Change to winetricks directory and install
        os.chdir("winetricks")
        success, _, _ = self.run_command(["sudo", "make", "install"])
        if not success:
            self.log("Failed to install winetricks", "error")
            return False

        # Go back to original directory
        os.chdir("..")

        # Clean up
        shutil.rmtree("winetricks")

        self.update_progress(1.0)
        self.update_progress_text("PikaOS dependencies installed")
        self.log("All dependencies installed for PikaOS", "success")
        return True

    def install_popos_dependencies(self):
        """Install Pop!_OS dependencies with WineHQ staging"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Pop!_OS Special Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log("Pop!_OS's built-in Wine has compatibility issues.", "warning")
        self.log("Setting up WineHQ staging from Ubuntu...\n", "info")

        # Total steps: keyrings, gpg key, i386, repo, apt update, wine install, deps install = 7 steps
        total_steps = 7
        current_step = 0

        # Create keyrings directory
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Creating keyrings directory..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Creating APT keyrings directory...", "info")
        success, _, _ = self.run_command(
            ["sudo", "mkdir", "-pm755", "/etc/apt/keyrings"]
        )
        if not success:
            self.log("Failed to create keyrings directory", "error")
            return False

        # Add GPG key
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ GPG key..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ GPG key...", "info")

        # Get sudo password for GPG operation
        password = self.get_sudo_password()
        if password is None:
            self.log("Authentication cancelled by user", "error")
            return False

        # Validate password if not already validated
        if not self.sudo_password_validated:
            if not self.validate_sudo_password(password):
                self.log("Authentication failed", "error")
                return False

        # Download GPG key to temporary file first (handles binary data correctly)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_key_path = tmp_file.name

        try:
            # Download the key in binary mode
            success, _, _ = self.run_command(
                [
                    "wget",
                    "-O",
                    tmp_key_path,
                    "https://dl.winehq.org/wine-builds/winehq.key",
                ]
            )
            if not success:
                self.log("Failed to download GPG key", "error")
                os.unlink(tmp_key_path)
                return False

            # Read the key file in binary mode
            with open(tmp_key_path, "rb") as key_file:
                key_data = key_file.read()

            # Clean up temp file
            os.unlink(tmp_key_path)

            # Remove existing key file to avoid overwrite prompts
            self.run_command(
                ["sudo", "rm", "-f", "/etc/apt/keyrings/winehq-archive.key"],
                check=False,
            )

            # Run GPG command with sudo, passing binary key data
            gpg_proc = subprocess.Popen(
                [
                    "sudo",
                    "-S",
                    "gpg",
                    "--dearmor",
                    "-o",
                    "/etc/apt/keyrings/winehq-archive.key",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Send password first (as bytes), then the key data (binary)
            gpg_input = f"{self.sudo_password}\n".encode() + key_data
            gpg_stdout, gpg_stderr = gpg_proc.communicate(input=gpg_input)

            if gpg_proc.returncode == 0:
                self.log("WineHQ GPG key added", "success")
            else:
                error_msg = (
                    gpg_stderr.decode("utf-8", errors="ignore")
                    if gpg_stderr
                    else "Unknown error"
                )
                self.log(f"Failed to add GPG key: {error_msg}", "error")
                return False
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(tmp_key_path):
                try:
                    os.unlink(tmp_key_path)
                except:
                    pass
            self.log(f"Failed to add GPG key: {str(e)}", "error")
            return False

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, _, _ = self.run_command(["sudo", "dpkg", "--add-architecture", "i386"])
        if not success:
            self.log("Failed to add i386 architecture", "error")
            return False

        # Add repository
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ repository..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ repository...", "info")
        # Get Ubuntu version codename
        codename = "jammy"
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("VERSION_CODENAME="):
                        codename = line.split("=")[1].strip()
        except (IOError, FileNotFoundError):
            pass  # Default to jammy

        # Remove existing file first to avoid overwrite prompt
        repo_file = Path(f"/etc/apt/sources.list.d/winehq-{codename}.sources")
        if repo_file.exists():
            self.run_command(["sudo", "rm", "-f", str(repo_file)], check=False)

        success, _, _ = self.run_command(
            [
                "sudo",
                "wget",
                "-P",
                "/etc/apt/sources.list.d/",
                f"https://dl.winehq.org/wine-builds/ubuntu/dists/{codename}/winehq-{codename}.sources",
            ]
        )
        if not success:
            self.log("Failed to add repository", "error")
            return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install WineHQ staging
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing WineHQ staging..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing WineHQ staging...", "info")
        success, _, _ = self.run_command(
            ["sudo", "apt", "install", "--install-recommends", "-y", "winehq-staging"]
        )
        if not success:
            self.log("Failed to install WineHQ staging", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "winetricks",
                "wget",
                "curl",
                "p7zip-full",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
            ]
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            self.log(
                "Note: dotnet-sdk-8.0 may require Microsoft's repository. You can install it manually if needed.",
                "warning",
            )
            return False

        self.update_progress(1.0)
        self.update_progress_text("Pop!_OS dependencies installed")
        self.log("All dependencies installed for Pop!_OS", "success")
        return True

    def install_ubuntu_based_dependencies(self):
        """Install dependencies for Ubuntu, Linux Mint, and Zorin OS with WineHQ staging"""
        print("DEBUG: install_ubuntu_based_dependencies() CALLED!", flush=True)
        self.log("===========================================", "info")
        self.log("★ Starting Ubuntu-based dependency installation ★", "warning")
        self.log(f"★ Detected distro: {self.distro} ★", "warning")
        self.log("===========================================", "info")
        distro_name = self.format_distro_name()
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log(f"{distro_name} Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Detect Ubuntu version codename
        codename = "jammy"
        ubuntu_version_num = 22.04
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("VERSION_CODENAME="):
                        codename = line.split("=")[1].strip()
                    if line.startswith("VERSION_ID="):
                        version_str = line.split("=")[1].strip().strip('"')
                        ubuntu_version_num = float(version_str)
        except (IOError, FileNotFoundError):
            pass

        # Linux Mint and Zorin may report their own version, need to detect base
        # Linux Mint 22 = Ubuntu 24.04 (noble), Linux Mint 21.x = Ubuntu 22.04 (jammy)
        # Zorin 18 = Ubuntu 24.04 (noble), Zorin 17.x = Ubuntu 22.04 (jammy)
        if self.distro == "linuxmint":
            # Force noble for Mint 22 - Mint 22 is based on Ubuntu 24.04
            # Check both VERSION_ID and DEBIAN_CODENAME
            detected_mint_version = ""
            detected_debian_codename = ""

            try:
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("VERSION_ID="):
                            detected_mint_version = (
                                line.split("=")[1].strip().strip('"')
                            )
                        if line.startswith("DEBIAN_CODENAME="):
                            detected_debian_codename = line.split("=")[1].strip()
            except:
                pass

            # Mint 22+ uses Ubuntu 24.04 (noble), older uses 22.04 (jammy)
            print(
                f"DEBUG: Mint version='{detected_mint_version}', debian_codename='{detected_debian_codename}'",
                flush=True,
            )
            if (
                detected_mint_version.startswith("22")
                or detected_debian_codename == "noble"
            ):
                codename = "noble"
                ubuntu_version_num = 24.04
            else:
                codename = "jammy"
                ubuntu_version_num = 22.04

        elif self.distro == "zorin":
            # Force noble for Zorin 18 - Zorin 18 is based on Ubuntu 24.04
            detected_zorin_version = ""
            detected_debian_codename = ""

            try:
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("VERSION_ID="):
                            detected_zorin_version = (
                                line.split("=")[1].strip().strip('"')
                            )
                        if line.startswith("DEBIAN_CODENAME="):
                            detected_debian_codename = line.split("=")[1].strip()
            except:
                pass

            # Zorin 18+ uses Ubuntu 24.04 (noble), older uses 22.04 (jammy)
            if (
                detected_zorin_version.startswith("18")
                or detected_debian_codename == "noble"
            ):
                codename = "noble"
                ubuntu_version_num = 24.04
            else:
                codename = "jammy"
                ubuntu_version_num = 22.04

        self.log(
            f"Detected codename: {codename}, version: {ubuntu_version_num}", "info"
        )

        # Debug: log raw os-release values for Mint/Zorin
        if self.distro in ["linuxmint", "zorin"]:
            try:
                with open("/etc/os-release", "r") as f:
                    content = f.read()
                # Just log the codename lines
                for line in content.split("\n"):
                    if "CODENAME" in line or "VERSION_ID" in line:
                        self.log(f"DEBUG: {line}", "info")
            except:
                pass

        # Validate codename is valid for WineHQ
        if codename not in ["noble", "jammy", "focal"]:
            self.log(
                f"Warning: codename '{codename}' may not have WineHQ packages. Using 'jammy' as fallback.",
                "warning",
            )
            codename = "jammy"

        # Check if we should use official Wine (Ubuntu 24.04+) or WineHQ staging
        # Note: Linux Mint 22 still uses WineHQ staging (better compatibility)
        is_mint = distro_name.lower() in ["linux mint", "mint", "zorin"]
        use_official_wine = ubuntu_version_num >= 24.04 and not is_mint

        if use_official_wine:
            self.log(
                f"Using official Wine packages for Ubuntu {ubuntu_version_num}...\n",
                "info",
            )
            return self.install_ubuntu_official_wine(codename)
        else:
            if is_mint:
                self.log(
                    f"Using WineHQ staging for {distro_name} (better compatibility)...\n",
                    "info",
                )
            else:
                self.log(f"Setting up WineHQ staging for {distro_name}...\n", "info")
            return self.install_ubuntu_winehq_staging(codename)

    def install_ubuntu_official_wine(self, codename):
        """Install Wine using official Ubuntu repositories for 24.04+"""
        distro_name = self.format_distro_name()
        total_steps = 4
        current_step = 0

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, _, _ = self.run_command(["sudo", "dpkg", "--add-architecture", "i386"])
        if not success:
            self.log("Failed to add i386 architecture", "error")
            return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install Wine
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing Wine..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing Wine (official Ubuntu packages)...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "wine",
                "wine64",
                "wine32",
                "libwine",
                "libwine:i386",
                "fonts-wine",
            ]
        )
        if not success:
            self.log("Failed to install Wine", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "winetricks",
                "wget",
                "curl",
                "p7zip-full",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ]
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            self.log(
                "Note: dotnet-sdk packages may require Microsoft's repository. You can install them manually if needed.",
                "warning",
            )
            return False

        self.update_progress(1.0)
        self.update_progress_text(f"{distro_name} dependencies installed")
        self.log(f"All dependencies installed for {distro_name}", "success")
        return True

    def install_ubuntu_winehq_staging(self, codename):
        """Install WineHQ staging for older Ubuntu versions (< 24.04)"""
        distro_name = self.format_distro_name()

        # Total steps: keyrings, gpg key, i386, repo, apt update, wine install, deps install = 7 steps
        total_steps = 7
        current_step = 0

        # Create keyrings directory
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Creating keyrings directory..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Creating APT keyrings directory...", "info")
        success, _, _ = self.run_command(
            ["sudo", "mkdir", "-pm755", "/etc/apt/keyrings"]
        )
        if not success:
            self.log("Failed to create keyrings directory", "error")
            return False

        # Add GPG key
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ GPG key..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ GPG key...", "info")

        # Get sudo password for GPG operation
        password = self.get_sudo_password()
        if password is None:
            self.log("Authentication cancelled by user", "error")
            return False

        # Validate password if not already validated
        if not self.sudo_password_validated:
            if not self.validate_sudo_password(password):
                self.log("Authentication failed", "error")
                return False

        # Download GPG key to temporary file first (handles binary data correctly)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_key_path = tmp_file.name

        try:
            # Download the key in binary mode
            success, _, _ = self.run_command(
                [
                    "wget",
                    "-O",
                    tmp_key_path,
                    "https://dl.winehq.org/wine-builds/winehq.key",
                ]
            )
            if not success:
                self.log("Failed to download GPG key", "error")
                os.unlink(tmp_key_path)
                return False

            # Read the key file in binary mode
            with open(tmp_key_path, "rb") as key_file:
                key_data = key_file.read()

            # Clean up temp file
            os.unlink(tmp_key_path)

            # Remove existing key file to avoid overwrite prompts
            self.run_command(
                ["sudo", "rm", "-f", "/etc/apt/keyrings/winehq-archive.key"],
                check=False,
            )

            # Run GPG command with sudo, passing binary key data
            gpg_proc = subprocess.Popen(
                [
                    "sudo",
                    "-S",
                    "gpg",
                    "--dearmor",
                    "-o",
                    "/etc/apt/keyrings/winehq-archive.key",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Send password first (as bytes), then the key data (binary)
            gpg_input = f"{self.sudo_password}\n".encode() + key_data
            gpg_stdout, gpg_stderr = gpg_proc.communicate(input=gpg_input)

            if gpg_proc.returncode == 0:
                self.log("WineHQ GPG key added", "success")
            else:
                error_msg = (
                    gpg_stderr.decode("utf-8", errors="ignore")
                    if gpg_stderr
                    else "Unknown error"
                )
                self.log(f"Failed to add GPG key: {error_msg}", "error")
                return False
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(tmp_key_path):
                try:
                    os.unlink(tmp_key_path)
                except:
                    pass
            self.log(f"Failed to add GPG key: {str(e)}", "error")
            return False

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, stdout, stderr = self.run_command(
            ["sudo", "dpkg", "--add-architecture", "i386"]
        )
        if not success:
            self.log(f"Failed to add i386 architecture - STDOUT: {stdout}", "error")
            self.log(f"Failed to add i386 architecture - STDERR: {stderr}", "error")
            return False
        else:
            self.log(f"Added i386 architecture successfully", "success")

        # Add repository
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ repository..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ repository...", "info")
        self.log(f"DEBUG: Using codename '{codename}' for WineHQ repo", "info")

        # Remove existing file first to avoid overwrite prompt
        repo_file = Path(f"/etc/apt/sources.list.d/winehq-{codename}.sources")
        if repo_file.exists():
            self.run_command(["sudo", "rm", "-f", str(repo_file)], check=False)

        repo_url = f"https://dl.winehq.org/wine-builds/ubuntu/dists/{codename}/winehq-{codename}.sources"
        self.log(f"DEBUG: Downloading repo from: {repo_url}", "info")
        self.log(
            f"DEBUG: Running command: sudo wget -NP /etc/apt/sources.list.d/ {repo_url}",
            "info",
        )

        # Use curl to download (no sudo needed), then sudo to move
        max_retries = 3
        for attempt in range(max_retries):
            # First download without sudo to /tmp
            success, stdout, stderr = self.run_command(
                ["curl", "-fsSL", "-o", f"/tmp/winehq-{codename}.sources", repo_url]
            )
            self.log(f"DEBUG: curl download exit code: {success}", "info")
            if not success:
                if stdout:
                    self.log(f"DEBUG: curl STDOUT:\n{stdout}", "info")
                if stderr:
                    self.log(f"DEBUG: curl STDERR:\n{stderr}", "info")

            # Check if file was downloaded to /tmp
            tmp_file = Path(f"/tmp/winehq-{codename}.sources")
            if tmp_file.exists():
                self.log(f"Downloaded to /tmp successfully", "success")

                # Now move to /etc/apt with sudo
                success2, stdout2, stderr2 = self.run_command(
                    [
                        "sudo",
                        "mv",
                        f"/tmp/winehq-{codename}.sources",
                        f"/etc/apt/sources.list.d/winehq-{codename}.sources",
                    ]
                )
                if success2:
                    self.log(f"Moved file to sources.list.d", "success")
                else:
                    self.log(
                        f"Failed to move file - STDOUT: {stdout2}, STDERR: {stderr2}",
                        "error",
                    )

            # Check if repo file exists
            repo_file = Path(f"/etc/apt/sources.list.d/winehq-{codename}.sources")

            # Debug: list all files in sources.list.d
            sources_dir = Path("/etc/apt/sources.list.d")
            if sources_dir.exists():
                files = list(sources_dir.glob("*"))
                self.log(
                    f"DEBUG: Files in sources.list.d: {[f.name for f in files]}", "info"
                )

            if repo_file.exists():
                self.log(f"WineHQ repository file found: {repo_file}", "success")
                break

            if attempt < max_retries - 1:
                self.log(
                    f"Warning: Repository file not found at {repo_file}, retrying... (attempt {attempt + 1}/{max_retries})",
                    "warning",
                )
            else:
                self.log("Failed to add repository after multiple attempts", "error")
                if stdout:
                    self.log(f"STDOUT: {stdout}", "error")
                if stderr:
                    self.log(f"STDERR: {stderr}", "error")
                return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install WineHQ staging
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing WineHQ staging..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing WineHQ staging...", "info")
        success, stdout, stderr = self.run_command(
            ["sudo", "apt", "install", "--install-recommends", "-y", "winehq-staging"]
        )
        if not success:
            self.log("Failed to install WineHQ staging", "error")
            if stdout:
                self.log(f"STDOUT: {stdout}", "error")
            if stderr:
                self.log(f"STDERR: {stderr}", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "winetricks",
                "wget",
                "curl",
                "p7zip-full",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ]
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            self.log(
                "Note: dotnet-sdk packages may require Microsoft's repository. You can install them manually if needed.",
                "warning",
            )
            return False

        self.update_progress(1.0)
        self.update_progress_text(f"{distro_name} dependencies installed")
        self.log(f"All dependencies installed for {distro_name}", "success")
        return True

    def setup_wine(self, wine_version="11.0"):
        """Setup Wine environment - installs custom Wine 9.14, 10.10, or 11.0 with AMD GPU and OpenCL patches

        Args:
            wine_version: "9.14" for Wine 9.14 (legacy), "10.10" for Wine 10.10, or "11.0" for Wine 11.0 (recommended)
        """
        self.start_operation("Setting up Wine environment")

        try:
            # Check if cancelled at start
            if self.check_cancelled():
                return False

            # First check that system Wine is available (needed for installation)
            system_wine = shutil.which("wine")
            if not system_wine:
                self.log(
                    "System Wine not found. System Wine is required for installation:",
                    "error",
                )
                self.log("  Ubuntu/Debian: sudo apt install wine", "info")
                self.log("  Fedora: sudo dnf install wine", "info")
                self.log("  Arch: sudo pacman -S wine", "info")
                self.update_progress_text("Ready")
                return False

            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Wine Binary Setup", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Get Wine version configuration
            config = self._get_wine_version_config(wine_version)
            wine_url = config["wine_url"]
            wine_file_name = config["wine_file_name"]
            wine_dir_name = config["wine_dir_name"]
            wine_dir_pattern = config["wine_dir_pattern"]
            archive_format = config["archive_format"]
            wine_display_name = config["wine_display_name"]

            self.log(f"Installing: {wine_display_name}", "info")

            # Stop Wine processes
            self.update_progress_text("Preparing Wine environment...")
            self.update_progress(0.0)
            self.log("Stopping Wine processes...", "info")
            self.run_command(["wineserver", "-k"], check=False)

            if self.check_cancelled():
                return False

            # Create directory
            self.update_progress_text("Creating installation directory...")
            self.update_progress(0.05)
            Path(self.directory).mkdir(parents=True, exist_ok=True)
            self.log("Installation directory created", "success")

            if self.check_cancelled():
                return False

            # Download Wine binary
            wine_file = Path(self.directory) / wine_file_name

            self.update_progress_text(f"Downloading {wine_display_name}...")
            self.update_progress(0.10)
            self.log(f"Downloading {wine_display_name}...", "info")
            if not self.download_file(
                wine_url, str(wine_file), f"{wine_display_name} binaries"
            ):
                self.log(f"Failed to download {wine_display_name}", "error")
                self.update_progress_text("Ready")
                return False

            if self.check_cancelled():
                return False

            # Extract Wine
            self.update_progress_text("Extracting Wine binary...")
            self.update_progress(0.50)
            self.log("Extracting Wine binary...", "info")
            try:
                if archive_format == "gz":
                    with tarfile.open(wine_file, "r:gz") as tar:
                        tar.extractall(self.directory, filter="data")
                elif archive_format == "xz":
                    try:
                        import lzma

                        with lzma.open(wine_file, "rb") as xz_file:
                            with tarfile.open(fileobj=xz_file, mode="r") as tar:
                                tar.extractall(self.directory, filter="data")
                    except ImportError:
                        if not self.check_command("xz") and not self.check_command(
                            "unxz"
                        ):
                            self.log(
                                "xz or unxz is required to extract Wine archive. Please install xz.",
                                "error",
                            )
                            self.update_progress_text("Ready")
                            return False
                        tar_file = wine_file.with_suffix(".tar")
                        xz_cmd = "xz" if self.check_command("xz") else "unxz"
                        success, _, _ = self.run_command(
                            [xz_cmd, "-d", "-k", str(wine_file)], check=True
                        )
                        if not success:
                            self.log("Failed to decompress Wine archive", "error")
                            self.update_progress_text("Ready")
                            return False
                        with tarfile.open(tar_file, "r") as tar:
                            tar.extractall(self.directory, filter="data")
                        tar_file.unlink()

                wine_file.unlink()
                self.log("Wine binary extracted", "success")
            except Exception as e:
                self.log(f"Failed to extract Wine: {e}", "error")
                self.update_progress_text("Ready")
                return False

            if self.check_cancelled():
                return False

            # Find and link Wine directory
            self.update_progress(0.55)
            wine_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
            if wine_dir and wine_dir != Path(self.directory) / wine_dir_name:
                target = Path(self.directory) / wine_dir_name
                if target.exists() or target.is_symlink():
                    if target.is_symlink():
                        target.unlink()
                    elif target.is_dir():
                        shutil.rmtree(target)
                target.symlink_to(wine_dir)
                self.log("Wine symlink created", "success")

            # Verify Wine binary
            self.update_progress(0.60)
            wine_binary = Path(self.directory) / wine_dir_name / "bin" / "wine"
            if not wine_binary.exists():
                self.log("Wine binary not found", "error")
                self.update_progress_text("Ready")
                return False

            self.log("Wine binary verified", "success")

            if self.check_cancelled():
                return False

            # Download icons
            self.update_progress_text("Downloading application icons...")
            self.update_progress(0.65)
            self.log("\nSetting up application icons...", "info")
            icons_dir = Path.home() / ".local" / "share" / "icons"
            icons_dir.mkdir(parents=True, exist_ok=True)

            icons = [
                (
                    "https://github.com/user-attachments/assets/c7b70ee5-58e3-46c6-b385-7c3d02749664",
                    icons_dir / "AffinityPhoto.svg",
                    "Photo icon",
                ),
                (
                    "https://github.com/user-attachments/assets/8ea7f748-c455-4ee8-9a94-775de40dbbf3",
                    icons_dir / "AffinityDesigner.svg",
                    "Designer icon",
                ),
                (
                    "https://github.com/user-attachments/assets/96ae06f8-470b-451f-ba29-835324b5b552",
                    icons_dir / "AffinityPublisher.svg",
                    "Publisher icon",
                ),
                (
                    "https://raw.githubusercontent.com/seapear/AffinityOnLinux/main/Assets/Icons/Affinity-Canva.svg",
                    icons_dir / "Affinity.svg",
                    "Affinity V3 icon",
                ),
            ]

            total_icons = len(icons)
            for idx, (url, path, desc) in enumerate(icons):
                if self.check_cancelled():
                    return False
                icon_progress = 0.65 + (idx / total_icons) * 0.05
                self.update_progress(icon_progress)
                if not self.download_file(url, str(path), desc):
                    self.log(
                        f"Warning: {desc} download failed, but continuing...", "warning"
                    )

            if self.check_cancelled():
                return False

            # Setup WinMetadata (only needed for Wine 9.14 and 10.10, not 11.0+)
            if wine_version in ["9.14", "10.10"]:
                self.update_progress_text("Setting up Windows Metadata...")
                self.update_progress(0.70)
                self.setup_winmetadata()
            else:
                self.log(
                    "Skipping WinMetadata setup for Wine 11.0+ (not needed)", "info"
                )

            if self.check_cancelled():
                return False

            # Cache all other Wine versions in background (for future switching)
            self.update_progress_text("Caching other Wine versions...")
            self.update_progress(0.72)
            self._download_all_wine_versions_to_cache(wine_version)

            if self.check_cancelled():
                return False

            if self.check_cancelled():
                return False

            # Setup vkd3d-proton (only if OpenCL is enabled and not AMD GPU)
            if self.is_opencl_enabled():
                gpu_id = self.get_selected_gpu()
                if self.has_nvidia_gpu() and (
                    gpu_id.startswith("nvidia_") or gpu_id.startswith("auto")
                ):
                    # Ask NVIDIA users to choose between DXVK and vkd3d
                    preference = self.ask_nvidia_dxvk_vkd3d_choice()
                    if preference == "dxvk":
                        self.update_progress_text(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs..."
                        )
                        self.update_progress(0.80)
                        self.log(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs and setting up DLL overrides",
                            "info",
                        )
                        self.install_d3d12_dlls()
                    else:
                        self.update_progress_text(
                            "Setting up vkd3d-proton for OpenCL..."
                        )
                        self.update_progress(0.80)
                        self.setup_vkd3d()
                elif self.has_amd_gpu() and (
                    gpu_id.startswith("amd_") or gpu_id.startswith("auto")
                ):
                    self.update_progress_text(
                        "AMD GPU detected - installing DXVK via winetricks..."
                    )
                    self.update_progress(0.80)
                    self.log(
                        "AMD GPU detected - installing DXVK via winetricks", "info"
                    )
                    self.install_dxvk_dlls()
                    self.log("Installing d3d12 DLLs for compatibility...", "info")
                    self.install_d3d12_dlls()
                else:
                    self.update_progress_text("Setting up vkd3d-proton for OpenCL...")
                    self.update_progress(0.80)
                    self.setup_vkd3d()
            else:
                self.update_progress_text("Installing d3d12 DLLs...")
                self.update_progress(0.80)
                self.log(
                    "OpenCL support is disabled, but installing d3d12 DLLs for compatibility",
                    "info",
                )
                self.install_d3d12_dlls()

            if self.check_cancelled():
                return False

            # Configure Wine
            self.update_progress_text("Configuring Wine with winetricks...")
            self.update_progress(0.90)
            self.configure_wine()

            if self.check_cancelled():
                return False

            self.setup_complete = True
            self.update_progress(1.0)
            self.update_progress_text("Wine setup complete!")
            self.log("\n✓ Wine setup completed!", "success")

            # Refresh installation status to update button states
            QTimer.singleShot(100, self.check_installation_status)
            return True

        except Exception as e:
            if not self.check_cancelled():
                self.log(f"Error setting up Wine environment: {e}", "error")
            return False

        finally:
            # Make sure to end the operation even if there was an error or cancellation
            if (
                hasattr(self, "current_operation")
                and self.current_operation == "Setting up Wine environment"
            ):
                self.end_operation()

    def _download_and_extract_winmetadata(self, extract_to_dir):
        """Download WinMetadata.tar.xz and extract it to the specified directory"""
        try:
            # Create temp directory for download
            temp_dir = Path(self.directory) / ".temp_winmetadata"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(exist_ok=True)

            winmetadata_url = "https://github.com/ryzendew/AffinityOnLinux/releases/download/10.4-Wine-Affinity/WinMetadata.tar.xz"
            winmetadata_file = temp_dir / "WinMetadata.tar.xz"

            self.log("Downloading WinMetadata...", "info")
            if not self.download_file(
                winmetadata_url, str(winmetadata_file), "WinMetadata"
            ):
                self.log("Failed to download WinMetadata", "error")
                return False

            self.log("Extracting WinMetadata...", "info")
            self.update_progress_text("Extracting Windows Metadata...")

            # Extract tar.xz file
            try:
                import lzma

                with lzma.open(winmetadata_file, "rb") as xz_file:
                    with tarfile.open(fileobj=xz_file, mode="r") as tar:
                        tar.extractall(extract_to_dir, filter="data")
            except ImportError:
                # Fallback to using xz command if lzma module is not available
                if not self.check_command("xz") and not self.check_command("unxz"):
                    self.log(
                        "xz or unxz is required to extract WinMetadata. Please install xz.",
                        "error",
                    )
                    return False
                tar_file = winmetadata_file.with_suffix(".tar")
                xz_cmd = "xz" if self.check_command("xz") else "unxz"
                success, _, _ = self.run_command(
                    [xz_cmd, "-d", "-k", str(winmetadata_file)], check=True
                )
                if not success:
                    self.log("Failed to decompress WinMetadata archive", "error")
                    return False
                with tarfile.open(tar_file, "r") as tar:
                    tar.extractall(extract_to_dir, filter="data")
                tar_file.unlink()

            # Clean up temp directory
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

            self.log("WinMetadata downloaded and extracted", "success")
            return True
        except Exception as e:
            self.log(f"Failed to download and extract WinMetadata: {e}", "error")
            return False

    def _download_wintypes_dll(self, output_path):
        """Download wintypes.dll to the specified path"""
        try:
            wintypes_url = "https://github.com/ElementalWarrior/wine-wintypes.dll-for-affinity/raw/refs/heads/master/wintypes_shim.dll.so"

            self.log("Downloading wintypes.dll...", "info")
            if not self.download_file(wintypes_url, str(output_path), "wintypes.dll"):
                self.log("Failed to download wintypes.dll", "error")
                return False

            self.log("wintypes.dll downloaded", "success")
            return True
        except Exception as e:
            self.log(f"Failed to download wintypes.dll: {e}", "error")
            return False

    def setup_winmetadata(self):
        """Download and install WinMetadata to system32"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Windows Metadata Installation", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        system32_dir.mkdir(parents=True, exist_ok=True)

        self.update_progress_text("Downloading Windows Metadata...")
        self.log("Downloading and installing Windows metadata...", "info")
        try:
            winmetadata_dest = system32_dir / "WinMetadata"

            # Remove existing WinMetadata if it exists
            if winmetadata_dest.exists():
                shutil.rmtree(winmetadata_dest)
                self.log("Removed existing WinMetadata folder", "info")

            # Download and extract WinMetadata
            if not self._download_and_extract_winmetadata(system32_dir):
                self.log("WinMetadata will not be installed", "warning")
                return

            # Verify WinMetadata was extracted
            if not winmetadata_dest.exists():
                self.log("WinMetadata extraction failed - folder not found", "error")
                return

            self.log("WinMetadata installed to system32", "success")
        except Exception as e:
            self.log(f"Failed to install WinMetadata: {e}", "error")

    def reinstall_winmetadata(self):
        """Remove old WinMetadata folder and reinstall fresh"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Reinstall WinMetadata", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please setup Wine environment first.", "error"
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before reinstalling WinMetadata.\n"
                "Please setup Wine environment first.",
            )
            return

        self.start_operation("Reinstall WinMetadata")
        threading.Thread(target=self._reinstall_winmetadata_entry, daemon=True).start()

    def _reinstall_winmetadata_entry(self):
        """Wrapper: reinstall WinMetadata and end operation."""
        try:
            self._reinstall_winmetadata_thread()
        finally:
            self.end_operation()

    def _reinstall_winmetadata_thread(self):
        """Reinstall WinMetadata in background thread"""
        # Kill Wine processes
        self.log("Stopping Wine processes...", "info")
        self.run_command(["wineserver", "-k"], check=False)
        time.sleep(2)

        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        winmetadata_dir = system32_dir / "WinMetadata"

        # Remove existing WinMetadata folder
        if winmetadata_dir.exists():
            self.log("Removing existing WinMetadata folder...", "info")
            try:
                shutil.rmtree(winmetadata_dir)
                self.log("Old WinMetadata folder removed", "success")
            except Exception as e:
                self.log(f"Warning: Could not fully remove old folder: {e}", "warning")

        # Ensure system32 directory exists
        system32_dir.mkdir(parents=True, exist_ok=True)

        # Reinstall WinMetadata by downloading and extracting (only for Wine < 11.0)
        wine_version = self.get_current_wine_version()
        if wine_version in ["9.14", "10.10"]:
            self.log("Installing fresh WinMetadata...", "info")
            self.setup_winmetadata()

            # Set up wintypes.dll override
            self.log("Setting up wintypes.dll override...", "info")
            self.setup_wintypes_dll_override()

            # Copy wintypes.dll for all installed Affinity apps (v2 and v3)
            self.log("Copying wintypes.dll for installed Affinity apps...", "info")
            self.copy_wintypes_dll_for_all_apps()
        else:
            self.log(
                "Skipping WinMetadata and wintypes.dll setup for Wine 11.0+ (not needed)",
                "info",
            )

        self.log("\n✓ WinMetadata reinstallation completed!", "success")

    def get_latest_vkd3d_version(self):
        """Get the latest vkd3d-proton version from GitHub releases API

        Returns:
            str: Latest version tag (e.g., "3.0a") or None if check fails
        """
        try:
            api_url = "https://api.github.com/repos/HansKristian-Work/vkd3d-proton/releases/latest"
            self.log("Checking for latest vkd3d-proton version...", "info")

            request = urllib.request.Request(api_url)
            request.add_header("User-Agent", "AffinityLinuxInstaller")

            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get("tag_name", "").lstrip(
                    "v"
                )  # Remove 'v' prefix if present

                if latest_version:
                    self.log(f"Latest vkd3d-proton version: {latest_version}", "info")
                    return latest_version
                else:
                    self.log("Could not determine latest version from API", "warning")
                    return None
        except urllib.error.URLError as e:
            self.log(f"Failed to check for latest vkd3d-proton version: {e}", "warning")
            return None
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse GitHub API response: {e}", "warning")
            return None
        except Exception as e:
            self.log(f"Error checking for latest vkd3d-proton version: {e}", "warning")
            return None

    def get_installed_vkd3d_version(self):
        """Get the currently installed vkd3d-proton version from cache

        Returns:
            str: Installed version or None if not found
        """
        version_file = Path(self.directory) / "dxvk" / ".vkd3d_version"
        if version_file.exists():
            try:
                return version_file.read_text().strip()
            except Exception:
                return None
        return None

    def set_installed_vkd3d_version(self, version):
        """Store the installed vkd3d-proton version

        Args:
            version: Version string to store
        """
        cache_dir = Path(self.directory) / "dxvk"
        cache_dir.mkdir(parents=True, exist_ok=True)
        version_file = cache_dir / ".vkd3d_version"
        try:
            version_file.write_text(version)
        except Exception as e:
            self.log(f"Failed to save vkd3d version: {e}", "warning")

    def get_latest_dxvk_version(self):
        """Get the latest DXVK version from GitHub releases API (normal version, not steamrt-sniper)

        Returns:
            str: Latest version tag (e.g., "2.3") or None if check fails
        """
        try:
            api_url = "https://api.github.com/repos/doitsujin/dxvk/releases/latest"
            self.log("Checking for latest DXVK version...", "info")

            request = urllib.request.Request(api_url)
            request.add_header("User-Agent", "AffinityLinuxInstaller")

            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get("tag_name", "").lstrip(
                    "v"
                )  # Remove 'v' prefix if present

                if latest_version:
                    self.log(f"Latest DXVK version: {latest_version}", "info")
                    return latest_version
                else:
                    self.log("Could not determine latest version from API", "warning")
                    return None
        except urllib.error.URLError as e:
            self.log(f"Failed to check for latest DXVK version: {e}", "warning")
            return None
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse GitHub API response: {e}", "warning")
            return None
        except Exception as e:
            self.log(f"Error checking for latest DXVK version: {e}", "warning")
            return None

    def get_installed_dxvk_version(self):
        """Check if DXVK is installed via winetricks

        Returns:
            str: "winetricks" if installed, None if not found
        """
        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        wine = self.get_wine_path("wine")

        dxvk_dlls = ["d3d8", "d3d9", "d3d11", "dxgi"]
        for dll in dxvk_dlls:
            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success and "native" in stdout:
                return "winetricks"
        return None

    def set_installed_dxvk_version(self, version):
        """Mark DXVK as installed (for compatibility)

        Args:
            version: Version string (typically "winetricks")
        """
        pass

    def install_dxvk_dlls(self):
        """Install DXVK using winetricks and ensure DLL overrides are set correctly

        DXVK is installed via winetricks which should handle DLL overrides, but we verify
        and set them up if needed to ensure proper functionality.
        """
        self.log("Installing DXVK via winetricks...", "info")

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        env["WINETRICKS_GUI"] = "0"
        env["DISPLAY"] = env.get("DISPLAY", ":0")
        env = self.get_winetricks_env_with_tkg(env)

        success = self.run_command_streaming(
            [
                "winetricks",
                "--unattended",
                "--verbose",
                "--force",
                "--no-isolate",
                "--optout",
                "dxvk",
            ],
            env=env,
            progress_callback=None,
        )

        # Always check for 64-bit DLLs regardless of winetricks success
        # (winetricks may fail but still install 32-bit DLLs, or may fail completely)
        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        dxvk_dll_names = [
            "d3d8.dll",
            "d3d9.dll",
            "d3d10.dll",
            "d3d10_1.dll",
            "d3d10core.dll",
            "d3d11.dll",
            "dxgi.dll",
        ]
        missing_64bit = [
            dll for dll in dxvk_dll_names if not (system32_dir / dll).exists()
        ]

        if missing_64bit:
            self.log(
                "64-bit DXVK DLLs missing in system32, downloading DXVK release...",
                "info",
            )
        latest_version = self.get_latest_dxvk_version()
        if not latest_version:
            latest_version = "2.3"

            dxvk_url = f"https://github.com/doitsujin/dxvk/releases/download/v{latest_version}/dxvk-{latest_version}.tar.gz"
            dxvk_file = Path(self.directory) / f"dxvk-{latest_version}.tar.gz"

            if self.download_file(dxvk_url, str(dxvk_file), "DXVK"):
                try:
                    import tarfile

                    with tarfile.open(dxvk_file, "r:gz") as tar:
                        extracted_count = 0
                        for member in tar.getmembers():
                            if member.name.startswith(
                                f"dxvk-{latest_version}/x64/"
                            ) and member.name.endswith(".dll"):
                                dll_name = Path(member.name).name
                                if dll_name in missing_64bit:
                                    member.name = dll_name
                                    tar.extract(member, system32_dir, filter="data")
                                    extracted_count += 1
                                    self.log(
                                        f"Extracted 64-bit {dll_name} to system32",
                                        "info",
                                    )

                        if extracted_count > 0:
                            self.log(
                                f"Extracted {extracted_count} 64-bit DXVK DLL(s) to system32",
                                "success",
                            )
                        else:
                            self.log("No 64-bit DLLs found in DXVK archive", "warning")
                except Exception as e:
                    self.log(f"Failed to extract DXVK: {e}", "warning")
                finally:
                    if dxvk_file.exists():
                        dxvk_file.unlink()
            else:
                self.log(
                    "Failed to download DXVK, DLLs may not work correctly", "warning"
                )
        else:
            self.log("64-bit DXVK DLLs verified in system32", "success")

        if success:
            self.log("DXVK installed via winetricks, verifying installation...", "info")
        else:
            self.log(
                "Winetricks installation failed, but continuing with manual DXVK setup...",
                "warning",
            )

        # Verify and set up DLL overrides (regardless of winetricks success)
        wine = self.get_wine_path("wine")
        dxvk_dlls = ["d3d8", "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "dxgi"]
        override_count = 0

        for dll in dxvk_dlls:
            success_check, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success_check and "native" in stdout:
                override_count += 1

        if override_count < len(dxvk_dlls):
            self.log("Setting up DLL overrides for DXVK...", "info")
            reg_file = Path(self.directory) / "dxvk_overrides.reg"
            with open(reg_file, "w") as f:
                f.write("REGEDIT4\n")
                f.write("[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]\n")
                for dll in dxvk_dlls:
                    f.write(f'"{dll}"="native,builtin"\n')

            regedit = self.get_wine_path("regedit")
            reg_success, _, stderr = self.run_command(
                [str(regedit), str(reg_file)], check=False, env=env, capture=True
            )
            reg_file.unlink()

            if reg_success:
                self.log("DXVK DLL overrides configured", "success")
            else:
                self.log(
                    f"Warning: Could not configure DLL overrides: {stderr}", "warning"
                )
        else:
            self.log(f"DXVK DLL overrides verified ({override_count} DLLs)", "success")

        self.set_installed_dxvk_version("winetricks")

    def install_d3d12_dlls(self):
        """Install d3d12.dll and d3d12core.dll from vkd3d-proton and set up DLL overrides"""
        self.log("Installing d3d12.dll and d3d12core.dll...", "info")

        # Get latest version or use default
        latest_version = self.get_latest_vkd3d_version()
        if not latest_version:
            # Fallback to current latest known version
            latest_version = "3.0a"
            self.log(f"Using fallback version: {latest_version}", "info")

        # Check if we need to update
        installed_version = self.get_installed_vkd3d_version()
        if installed_version and installed_version == latest_version:
            self.log(f"vkd3d-proton {latest_version} is already installed", "info")
        elif installed_version:
            self.log(
                f"Updating vkd3d-proton from {installed_version} to {latest_version}",
                "info",
            )
            # Clear old cache if version changed
            cache_dir = Path(self.directory) / "dxvk"
            old_cached_dir = cache_dir / f"vkd3d-proton-{installed_version}"
            if old_cached_dir.exists():
                try:
                    shutil.rmtree(old_cached_dir)
                    self.log(f"Removed old cached version {installed_version}", "info")
                except Exception as e:
                    self.log(f"Warning: Could not remove old cache: {e}", "warning")

        vkd3d_version = latest_version
        vkd3d_url = f"https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v{vkd3d_version}/vkd3d-proton-{vkd3d_version}.tar.zst"
        vkd3d_file_name = f"vkd3d-proton-{vkd3d_version}.tar.zst"
        cache_dir = Path(self.directory) / "dxvk"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_vkd3d_file = cache_dir / vkd3d_file_name
        cached_vkd3d_dir = cache_dir / f"vkd3d-proton-{vkd3d_version}"
        vkd3d_temp = Path(self.directory) / "vkd3d_dlls"
        vkd3d_temp.mkdir(exist_ok=True)

        # Check if DLLs already exist
        wine_lib_dir = (
            self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
        )
        if (
            wine_lib_dir.exists()
            and (wine_lib_dir / "d3d12.dll").exists()
            and (wine_lib_dir / "d3d12core.dll").exists()
        ):
            self.log("d3d12 DLLs already installed", "info")
            self.setup_d3d12_overrides()
            return

        # Check cache first
        vkd3d_dir = None
        if cached_vkd3d_dir.exists():
            self.log("Using cached vkd3d-proton...", "info")
            vkd3d_dir = cached_vkd3d_dir
        else:
            # Download vkd3d-proton
            self.log("Downloading vkd3d-proton for d3d12 DLLs...", "info")
            vkd3d_file = Path(self.directory) / vkd3d_file_name
            if not self.download_file(vkd3d_url, str(vkd3d_file), "vkd3d-proton"):
                self.log("Failed to download vkd3d-proton", "error")
                return

            # Cache the downloaded file
            shutil.copy2(vkd3d_file, cached_vkd3d_file)
            self.log("Cached vkd3d-proton archive", "success")

            # Extract vkd3d-proton
            self.log("Extracting vkd3d-proton...", "info")
            if self.check_command("unzstd"):
                tar_file = Path(self.directory) / "vkd3d-proton.tar"
                success, _, _ = self.run_command(
                    ["unzstd", "-f", str(vkd3d_file), "-o", str(tar_file)]
                )
                if success:
                    with tarfile.open(tar_file, "r") as tar:
                        tar.extractall(self.directory, filter="data")
                    tar_file.unlink()
                    self.log("vkd3d-proton extracted", "success")

            vkd3d_file.unlink()

            # Find extracted directory and cache it
            vkd3d_dir = next(Path(self.directory).glob("vkd3d-proton-*"), None)
            if vkd3d_dir:
                # Cache the extracted directory
                shutil.copytree(vkd3d_dir, cached_vkd3d_dir)
                self.log("Cached vkd3d-proton directory", "success")
            else:
                self.log("Failed to find extracted vkd3d-proton directory", "error")
                return

        # Copy DLLs
        if vkd3d_dir:
            wine_lib_dir.mkdir(parents=True, exist_ok=True)

            for dll in ["d3d12.dll", "d3d12core.dll"]:
                for source_dir in [vkd3d_dir / "x64", vkd3d_dir]:
                    src = source_dir / dll
                    if src.exists():
                        shutil.copy2(src, vkd3d_temp / dll)
                        shutil.copy2(src, wine_lib_dir / dll)
                        self.log(f"Installed {dll}", "success")
                        break

            # Only remove if it's not the cached version
            if vkd3d_dir != cached_vkd3d_dir:
                shutil.rmtree(vkd3d_dir)

            # Store installed version
            self.set_installed_vkd3d_version(vkd3d_version)
            self.log(f"d3d12 DLLs installed (vkd3d-proton {vkd3d_version})", "success")

        # Set up DLL overrides
        self.setup_d3d12_overrides()

    def setup_d3d12_overrides(self):
        """Set up DLL overrides for d3d12.dll and d3d12core.dll"""
        self.log("Setting up DLL overrides for d3d12...", "info")

        reg_file = Path(self.directory) / "dll_overrides.reg"
        with open(reg_file, "w") as f:
            f.write("REGEDIT4\n")
            f.write("[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]\n")
            f.write('"d3d12"="native"\n')
            f.write('"d3d12core"="native"\n')

        regedit = self.get_wine_path("regedit")
        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        success, _, stderr = self.run_command(
            [str(regedit), str(reg_file)], check=False, env=env, capture=True
        )
        reg_file.unlink()

        if success:
            self.log("DLL overrides configured for d3d12", "success")
        else:
            self.log(f"Warning: Could not configure DLL overrides: {stderr}", "warning")

    def setup_dxvk_overrides(self):
        """
        Set up DLL overrides for DXVK in Wine registry

        DXVK is installed via winetricks which automatically sets up DLL overrides.
        This function verifies the installation and ensures overrides are correct.
        """
        self.log("Verifying DXVK installation via winetricks...", "info")

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        env["WINETRICKS_GUI"] = "0"
        env["DISPLAY"] = env.get("DISPLAY", ":0")
        env = self.get_winetricks_env_with_tkg(env)

        wine = self.get_wine_path("wine")

        dxvk_dlls = ["d3d8", "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "dxgi"]
        override_count = 0

        for dll in dxvk_dlls:
            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success and "native" in stdout:
                override_count += 1

        if override_count > 0:
            self.log(f"DXVK DLL overrides verified ({override_count} DLLs)", "success")
        else:
            self.log(
                "DXVK DLL overrides not found - winetricks should have set them up",
                "warning",
            )
            self.log("Installing DXVK via winetricks to set up overrides...", "info")
            self.install_dxvk_dlls()

    def remove_dxvk_overrides(self):
        """Remove DXVK via winetricks and clean up DLL overrides"""
        self.log("Removing DXVK via winetricks...", "info")

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        env["WINETRICKS_GUI"] = "0"
        env["DISPLAY"] = env.get("DISPLAY", ":0")
        env = self.get_winetricks_env_with_tkg(env)

        wine = self.get_wine_path("wine")

        dxvk_dlls = ["d3d8", "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "dxgi"]
        removed_count = 0

        for dll in dxvk_dlls:
            success, _, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "delete",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                    "/f",
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success:
                removed_count += 1

        if removed_count > 0:
            self.log(f"Removed {removed_count} DXVK DLL override(s)", "success")
        else:
            self.log("No DXVK DLL overrides found to remove", "info")

        self.remove_dxvk_dlls_from_system32()

        cache_dir = Path(self.directory) / "dxvk"
        if cache_dir.exists():
            try:
                shutil.rmtree(cache_dir)
                self.log("Removed DXVK cache directory", "success")
            except Exception as e:
                self.log(f"Warning: Could not remove DXVK cache: {e}", "warning")

    def remove_dxvk_dlls_from_system32(self):
        """Remove DXVK DLLs from system32 directory"""
        self.log("Removing DXVK DLLs from system32...", "info")

        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        dxvk_dlls = ["d3d8.dll", "d3d9.dll", "d3d10core.dll", "d3d11.dll", "dxgi.dll"]
        removed_count = 0

        for dll in dxvk_dlls:
            dll_path = system32_dir / dll
            if dll_path.exists():
                try:
                    dll_path.unlink()
                    self.log(f"Removed {dll} from system32", "success")
                    removed_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove {dll} from system32: {e}", "warning"
                    )

        if removed_count > 0:
            self.log(f"Removed {removed_count} DXVK DLL(s) from system32", "success")
        else:
            self.log("No DXVK DLLs found in system32 to remove", "info")

    def remove_d3d12_overrides(self):
        """Remove DLL overrides for vkd3d (d3d12, d3d12core)"""
        self.log("Removing DLL overrides for vkd3d...", "info")

        wine = self.get_wine_path("wine")
        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        vkd3d_dlls = ["d3d12", "d3d12core"]
        removed_count = 0

        for dll in vkd3d_dlls:
            success, _, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "delete",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                    "/f",
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success:
                removed_count += 1

        if removed_count > 0:
            self.log(f"Removed {removed_count} vkd3d DLL override(s)", "success")
        else:
            self.log("No vkd3d DLL overrides found to remove", "info")

    def setup_vkd3d(self):
        """Setup vkd3d-proton for OpenCL"""
        # Check NVIDIA GPU preference
        if self.has_nvidia_gpu():
            preference = self.get_dxvk_vkd3d_preference()
            if preference == "dxvk":
                self.log(
                    "NVIDIA GPU with DXVK preference - skipping vkd3d-proton installation",
                    "info",
                )
                # Still install d3d12 DLLs and overrides
                self.install_d3d12_dlls()
                return

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("OpenCL Support Setup", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Get latest version or use default
        latest_version = self.get_latest_vkd3d_version()
        if not latest_version:
            # Fallback to current latest known version
            latest_version = "3.0a"
            self.log(f"Using fallback version: {latest_version}", "info")

        # Check if we need to update
        installed_version = self.get_installed_vkd3d_version()
        if installed_version and installed_version == latest_version:
            self.log(f"vkd3d-proton {latest_version} is already installed", "info")
        elif installed_version:
            self.log(
                f"Updating vkd3d-proton from {installed_version} to {latest_version}",
                "info",
            )

        vkd3d_version = latest_version
        vkd3d_url = f"https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v{vkd3d_version}/vkd3d-proton-{vkd3d_version}.tar.zst"
        vkd3d_file = Path(self.directory) / f"vkd3d-proton-{vkd3d_version}.tar.zst"
        vkd3d_temp = Path(self.directory) / "vkd3d_dlls"
        vkd3d_temp.mkdir(exist_ok=True)

        self.update_progress_text("Downloading vkd3d-proton...")
        self.log(f"Downloading vkd3d-proton {vkd3d_version}...", "info")
        if not self.download_file(vkd3d_url, str(vkd3d_file), "vkd3d-proton"):
            self.log("Failed to download vkd3d-proton", "error")
            return

        # Extract vkd3d-proton
        self.update_progress_text("Extracting vkd3d-proton...")
        self.log("Extracting vkd3d-proton...", "info")
        if self.check_command("unzstd"):
            tar_file = Path(self.directory) / "vkd3d-proton.tar"
            success, _, _ = self.run_command(
                ["unzstd", "-f", str(vkd3d_file), "-o", str(tar_file)]
            )
            if success:
                with tarfile.open(tar_file, "r") as tar:
                    tar.extractall(self.directory, filter="data")
                tar_file.unlink()
                self.log("vkd3d-proton extracted", "success")

        vkd3d_file.unlink()

        # Copy DLLs
        vkd3d_dir = next(Path(self.directory).glob("vkd3d-proton-*"), None)
        if vkd3d_dir:
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            wine_lib_dir.mkdir(parents=True, exist_ok=True)

            for dll in ["d3d12.dll", "d3d12core.dll"]:
                for source_dir in [vkd3d_dir / "x64", vkd3d_dir]:
                    src = source_dir / dll
                    if src.exists():
                        shutil.copy2(src, vkd3d_temp / dll)
                        shutil.copy2(src, wine_lib_dir / dll)
                        self.log(f"Copied {dll}", "success")
                        break

            shutil.rmtree(vkd3d_dir)

            # Store installed version
            self.set_installed_vkd3d_version(vkd3d_version)
            self.log(
                f"vkd3d-proton setup completed (version {vkd3d_version})", "success"
            )

        # Set up DLL overrides
        self.setup_d3d12_overrides()

    def configure_wine(self):
        """Configure Wine with winetricks"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Wine Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Ensure wine-tkg is available for winetricks
        self.log("Setting up wine-tkg for winetricks...", "info")
        sys.stderr.write("\n[WINE-TKG] Calling ensure_wine_tkg() for winetricks...\n")
        sys.stderr.flush()
        wine_tkg_result = self.ensure_wine_tkg()
        sys.stderr.write(f"[WINE-TKG] ensure_wine_tkg() returned: {wine_tkg_result}\n")
        sys.stderr.flush()
        if not wine_tkg_result:
            error_msg = "Failed to setup wine-tkg, continuing with system wine"
            sys.stderr.write(f"[WINE-TKG] WARNING: {error_msg}\n")
            sys.stderr.flush()
            self.log(error_msg, "warning")

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        # Prevent winetricks from showing GUI dialogs
        env["WINETRICKS_GUI"] = "0"
        env["DISPLAY"] = env.get(
            "DISPLAY", ":0"
        )  # Ensure display is set but winetricks won't use GUI

        # Use wine-tkg for winetricks if available
        env = self.get_winetricks_env_with_tkg(env)

        wine_cfg = self.get_wine_path("winecfg")

        components = [
            "dotnet35sp1",
            "dotnet48",
            "corefonts",
            "vcrun2022",
            "msxml3",
            "msxml6",
            "tahoma",
            "renderer=vulkan",
            "crypt32",
        ]

        self.log(
            "Installing Wine components (this may take several minutes)...", "info"
        )
        total_components = len(components)
        for idx, component in enumerate(components):
            # Calculate base progress for this component (0.0 to 1.0 across all components)
            base_progress = idx / total_components
            component_progress_range = 1.0 / total_components

            # Update progress label to show current component
            self.update_progress_text(
                f"Installing: {component} ({idx + 1}/{total_components})"
            )

            self.log(
                f"Installing {component}... [{idx + 1}/{total_components}]", "info"
            )
            self.log("  (Progress will be shown below)", "info")

            # Progress callback that updates based on component progress
            def update_component_progress(percent):
                # percent is 0.0-1.0 for this component
                # Map it to overall progress
                overall_progress = base_progress + (percent * component_progress_range)
                self.update_progress(overall_progress)

            # Use streaming to show progress
            self.run_command_streaming(
                [
                    "winetricks",
                    "--unattended",
                    "--verbose",
                    "--force",
                    "--no-isolate",
                    "--optout",
                    component,
                ],
                env=env,
                progress_callback=update_component_progress,
            )

            # Mark this component as complete
            self.update_progress(base_progress + component_progress_range)

        # Set Windows version to 11
        self.log("Setting Windows version to 11...", "info")
        self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

        # Apply dark theme
        self.log("Applying Wine dark theme...", "info")
        theme_file = Path(self.directory) / "wine-dark-theme.reg"
        if self.download_file(
            "https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Auxiliary/Other/wine-dark-theme.reg",
            str(theme_file),
            "dark theme",
        ):
            regedit = self.get_wine_path("regedit")
            self.run_command([str(regedit), str(theme_file)], check=False, env=env)
            theme_file.unlink()

        self.log("Wine configuration completed", "success")
        self.update_progress_text("Ready")

    def show_main_menu(self):
        """Display main application menu"""
        self.log("\n✓ Setup complete! Select an application to install:", "success")
        self.update_progress(1.0)

    def setup_wine_environment(self):
        """Setup Wine environment only"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Setup Wine Environment", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Ask user to choose Wine version
        wine_version = self.show_question_dialog(
            "Choose Wine Version",
            "Which Wine version would you like to install?\n\n"
            "• Wine 11.0 (Recommended) - ElementalWarrior Wine 11.0 with AMD GPU and OpenCL patches. Latest version with best compatibility and performance.\n"
            "• Wine 10.10 - ElementalWarrior Wine 10.10 with AMD GPU and OpenCL patches. Previous stable version.\n"
            "• Wine 9.14 (Legacy) - Legacy version with AMD GPU and OpenCL patches. Fallback option if you encounter issues with newer versions.\n\n"
            "Note: You can switch versions later by running this setup again.",
            ["Wine 11.0 (Recommended)", "Wine 10.10", "Wine 9.14 (Legacy)"],
        )

        if wine_version == "Wine 11.0 (Recommended)":
            wine_version_choice = "11.0"
        elif wine_version == "Wine 10.10":
            wine_version_choice = "10.10"
        elif wine_version == "Wine 9.14 (Legacy)":
            wine_version_choice = "9.14"
        else:
            self.log("Wine setup cancelled", "warning")
            return

        threading.Thread(
            target=self.setup_wine, args=(wine_version_choice,), daemon=True
        ).start()

    def _get_wine_version_config(self, wine_version):
        """Get Wine version configuration (URL, filename, etc.)

        Args:
            wine_version: "9.14", "10.10", or "11.0"

        Returns:
            dict with wine_url, wine_file_name, wine_dir_name, wine_dir_pattern, archive_format, wine_display_name
        """
        if wine_version == "9.14":
            return {
                "wine_url": "https://github.com/seapear/AffinityOnLinux/releases/download/Legacy/ElementalWarriorWine-x86_64.tar.gz",
                "wine_file_name": "ElementalWarriorWine-x86_64.tar.gz",
                "wine_dir_name": "ElementalWarriorWine",
                "wine_dir_pattern": "ElementalWarriorWine*",
                "archive_format": "gz",
                "wine_display_name": "Wine 9.14 (Legacy - with AMD GPU and OpenCL patches)",
            }
        elif wine_version == "10.10":
            return {
                "wine_url": "https://github.com/ryzendew/Affinity-Wine-Builder/releases/download/10.10/ElementalWarrior-wine-10.10.tar.xz",
                "wine_file_name": "ElementalWarrior-wine-10.10.tar.xz",
                "wine_dir_name": "ElementalWarriorWine",
                "wine_dir_pattern": "ElementalWarrior-wine-10.10*",
                "archive_format": "xz",
                "wine_display_name": "Wine 10.10 (with AMD GPU and OpenCL patches)",
            }
        else:  # Default to 11.0
            return {
                "wine_url": "https://github.com/ryzendew/Affinity-Wine-Builder/releases/download/11.0/ElementalWarrior-wine-11.0.tar.xz",
                "wine_file_name": "ElementalWarrior-wine-11.0.tar.xz",
                "wine_dir_name": "ElementalWarriorWine",
                "wine_dir_pattern": "ElementalWarrior-wine-11.0*",
                "archive_format": "xz",
                "wine_display_name": "Wine 11.0 (Latest - with AMD GPU and OpenCL patches)",
            }

    def _download_wine_to_cache(self, wine_version, cache_dir):
        """Download a Wine version to cache directory

        Args:
            wine_version: "9.14", "10.10", or "11.0"
            cache_dir: Path to cache directory

        Returns:
            True if successful, False otherwise
        """
        config = self._get_wine_version_config(wine_version)
        wine_file = cache_dir / config["wine_file_name"]
        wine_dir = cache_dir / wine_version

        # Check if already cached
        if wine_dir.exists() and (wine_dir / "bin" / "wine").exists():
            self.log(
                f"{config['wine_display_name']} already cached, skipping download",
                "info",
            )
            return True

        # Download Wine binary
        self.log(f"Caching {config['wine_display_name']}...", "info")
        if not self.download_file(
            config["wine_url"],
            str(wine_file),
            f"{config['wine_display_name']} binaries",
        ):
            self.log(f"Failed to cache {config['wine_display_name']}", "warning")
            return False

        if self.check_cancelled():
            return False

        # Extract Wine
        self.log(f"Extracting {config['wine_display_name']}...", "info")
        try:
            if config["archive_format"] == "gz":
                with tarfile.open(wine_file, "r:gz") as tar:
                    tar.extractall(cache_dir, filter="data")
            elif config["archive_format"] == "xz":
                try:
                    import lzma

                    with lzma.open(wine_file, "rb") as xz_file:
                        with tarfile.open(fileobj=xz_file, mode="r") as tar:
                            tar.extractall(cache_dir, filter="data")
                except ImportError:
                    if not self.check_command("xz") and not self.check_command("unxz"):
                        self.log(
                            "xz or unxz is required to extract Wine archive. Please install xz.",
                            "warning",
                        )
                        wine_file.unlink()
                        return False
                    tar_file = wine_file.with_suffix(".tar")
                    xz_cmd = "xz" if self.check_command("xz") else "unxz"
                    success, _, _ = self.run_command(
                        [xz_cmd, "-d", "-k", str(wine_file)], check=True
                    )
                    if not success:
                        self.log("Failed to decompress Wine archive", "warning")
                        wine_file.unlink()
                        return False
                    with tarfile.open(tar_file, "r") as tar:
                        tar.extractall(cache_dir, filter="data")
                    tar_file.unlink()

            wine_file.unlink()

            # Find extracted directory and rename to version name
            extracted_dir = next(cache_dir.glob(config["wine_dir_pattern"]), None)
            if extracted_dir:
                if extracted_dir != wine_dir:
                    if wine_dir.exists():
                        shutil.rmtree(wine_dir)
                    extracted_dir.rename(wine_dir)
                self.log(f"Cached {config['wine_display_name']}", "success")
                return True
            else:
                self.log(
                    f"Could not find extracted Wine directory for {wine_version}",
                    "warning",
                )
                return False

        except Exception as e:
            self.log(f"Failed to extract cached Wine {wine_version}: {e}", "warning")
            if wine_file.exists():
                wine_file.unlink()
            return False

    def _download_all_wine_versions_to_cache(self, selected_version):
        """Download all Wine versions to cache directory (except the one already being installed)

        Args:
            selected_version: The version that's already being downloaded/installed
        """
        cache_dir = Path(self.directory) / "Wine-Switch"
        cache_dir.mkdir(parents=True, exist_ok=True)

        all_versions = ["9.14", "10.10"]

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Caching All Wine Versions", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log(
            "Downloading all Wine versions to cache for future switching...", "info"
        )
        self.log(
            "This helps users with capped internet by avoiding re-downloads.\n", "info"
        )

        for version in all_versions:
            if version == selected_version:
                # Already downloading this one, skip
                continue

            if self.check_cancelled():
                return

            self._download_wine_to_cache(version, cache_dir)

        self.log("\n✓ All Wine versions cached successfully!", "success")

    def _cache_dxvk(self):
        """DXVK is now handled by winetricks, which manages its own caching.

        This function is kept for compatibility but no longer performs manual caching.
        """
        self.log("DXVK caching is handled automatically by winetricks", "info")

    def _check_and_update_dxvk_vkd3d(self):
        """Check if DXVK or vkd3d-proton need updating and update them if needed
        Also download DXVK if missing.
        Runs in background thread to avoid blocking GUI.
        """
        threading.Thread(
            target=self._check_and_update_dxvk_vkd3d_thread, daemon=True
        ).start()

    def _check_and_update_dxvk_vkd3d_thread(self):
        """Background thread to check DXVK/vkd3d-proton status"""
        try:
            # Only check if Wine is already set up
            wine_dir = self.get_wine_dir()
            if not wine_dir.exists():
                return  # Wine not set up yet, skip check

            self.log("Checking DXVK and vkd3d-proton status...", "info")

            # Check if DXVK is installed via winetricks
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            wine = self.get_wine_path("wine")

            dxvk_installed = False
            dxvk_dlls = ["d3d8", "d3d9", "d3d11", "dxgi"]
            for dll in dxvk_dlls:
                success, stdout, _ = self.run_command(
                    [
                        str(wine),
                        "reg",
                        "query",
                        "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                        "/v",
                        dll,
                    ],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success and "native" in stdout:
                    dxvk_installed = True
                    break

            if dxvk_installed:
                self.log("DXVK is installed via winetricks", "info")
            else:
                if self.has_amd_gpu():
                    self.log(
                        "AMD GPU detected - DXVK should be installed via winetricks",
                        "info",
                    )
                else:
                    self.log(
                        "DXVK not installed (will be installed when switching to DXVK)",
                        "info",
                    )

            # Check vkd3d-proton
            latest_vkd3d = self.get_latest_vkd3d_version()
            if latest_vkd3d:
                installed_vkd3d = self.get_installed_vkd3d_version()
                cache_dir = Path(self.directory) / "dxvk"
                cached_vkd3d_dir = cache_dir / f"vkd3d-proton-{latest_vkd3d}"

                # Check if vkd3d-proton is missing or outdated
                if not installed_vkd3d or installed_vkd3d != latest_vkd3d:
                    if not cached_vkd3d_dir.exists():
                        self.log(
                            f"vkd3d-proton {latest_vkd3d} is missing or outdated, will download when needed",
                            "info",
                        )
                    elif installed_vkd3d != latest_vkd3d:
                        self.log(
                            f"vkd3d-proton update available: {installed_vkd3d} -> {latest_vkd3d}",
                            "info",
                        )
                        self.log(
                            "Update will be downloaded when switching to vkd3d", "info"
                        )

            self.log("DXVK and vkd3d-proton check completed", "success")

        except Exception as e:
            self.log(f"Error checking DXVK/vkd3d-proton updates: {e}", "warning")

    def _setup_wine_switch(self, wine_version="10.10"):
        """Setup Wine binary only - for switching versions without reconfiguration

        Args:
            wine_version: "9.14" for Wine 9.14 (legacy), or "10.10" for Wine 10.10 (recommended)
        """
        try:
            # Get Wine version configuration
            config = self._get_wine_version_config(wine_version)
            wine_url = config["wine_url"]
            wine_file_name = config["wine_file_name"]
            wine_dir_name = config["wine_dir_name"]
            wine_dir_pattern = config["wine_dir_pattern"]
            archive_format = config["archive_format"]
            wine_display_name = config["wine_display_name"]

            # Check cache first
            cache_dir = Path(self.directory) / "Wine-Switch"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached_wine_dir = cache_dir / wine_version

            if cached_wine_dir.exists() and (cached_wine_dir / "bin" / "wine").exists():
                # Use cached version
                self.log(f"Using cached {wine_display_name}...", "info")
                self.update_progress_text(f"Using cached {wine_display_name}...")
                self.update_progress(0.3)

                # Create directory
                Path(self.directory).mkdir(parents=True, exist_ok=True)

                if self.check_cancelled():
                    return False

                # Copy from cache
                self.update_progress_text("Copying Wine from cache...")
                self.update_progress(0.5)
                self.log("Copying Wine from cache...", "info")

                # Find and link Wine directory
                wine_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
                if wine_dir and wine_dir != Path(self.directory) / wine_dir_name:
                    target = Path(self.directory) / wine_dir_name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        elif target.is_dir():
                            shutil.rmtree(target)
                    target.symlink_to(wine_dir)
                else:
                    # Copy from cache
                    target = Path(self.directory) / wine_dir_name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        elif target.is_dir():
                            shutil.rmtree(target)
                    shutil.copytree(cached_wine_dir, target)

                self.log("Wine copied from cache", "success")
            else:
                # Download and cache
                self.log(
                    f"Selected version: {wine_version} -> Downloading: {wine_display_name}",
                    "info",
                )
                self.log(f"Download URL: {wine_url}", "info")

                # Create directory
                Path(self.directory).mkdir(parents=True, exist_ok=True)

                if self.check_cancelled():
                    return False

                # Download Wine binary
                wine_file = Path(self.directory) / wine_file_name
                self.update_progress_text(f"Downloading {wine_display_name}...")
                self.update_progress(0.4)
                self.log(f"Downloading {wine_display_name}...", "info")
                if not self.download_file(
                    wine_url, str(wine_file), f"{wine_display_name} binaries"
                ):
                    self.log(f"Failed to download {wine_display_name}", "error")
                    return False

                if self.check_cancelled():
                    return False

                # Extract Wine
                self.update_progress_text("Extracting Wine binary...")
                self.update_progress(0.6)
                self.log("Extracting Wine binary...", "info")
                try:
                    if archive_format == "gz":
                        with tarfile.open(wine_file, "r:gz") as tar:
                            tar.extractall(self.directory, filter="data")
                    elif archive_format == "xz":
                        try:
                            import lzma

                            with lzma.open(wine_file, "rb") as xz_file:
                                with tarfile.open(fileobj=xz_file, mode="r") as tar:
                                    tar.extractall(self.directory, filter="data")
                        except ImportError:
                            if not self.check_command("xz") and not self.check_command(
                                "unxz"
                            ):
                                self.log(
                                    "xz or unxz is required to extract Wine archive. Please install xz.",
                                    "error",
                                )
                                return False
                            tar_file = wine_file.with_suffix(".tar")
                            xz_cmd = "xz" if self.check_command("xz") else "unxz"
                            success, _, _ = self.run_command(
                                [xz_cmd, "-d", "-k", str(wine_file)], check=True
                            )
                            if not success:
                                self.log("Failed to decompress Wine archive", "error")
                                return False
                            with tarfile.open(tar_file, "r") as tar:
                                tar.extractall(self.directory, filter="data")
                            tar_file.unlink()

                    wine_file.unlink()
                    self.log("Wine binary extracted", "success")
                except Exception as e:
                    self.log(f"Failed to extract Wine: {e}", "error")
                    return False

                # Cache this version for future use
                cache_dir.mkdir(parents=True, exist_ok=True)
                extracted_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
                if extracted_dir:
                    cached_wine_dir = cache_dir / wine_version
                    if cached_wine_dir.exists():
                        shutil.rmtree(cached_wine_dir)
                    shutil.copytree(extracted_dir, cached_wine_dir)
                    self.log(f"Cached {wine_display_name} for future use", "success")

                if self.check_cancelled():
                    return False

                # Find and link Wine directory
                self.update_progress(0.8)
                wine_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
                if wine_dir and wine_dir != Path(self.directory) / wine_dir_name:
                    target = Path(self.directory) / wine_dir_name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        elif target.is_dir():
                            shutil.rmtree(target)
                    target.symlink_to(wine_dir)
                    self.log("Wine symlink created", "success")

            # Verify Wine binary
            self.update_progress(0.9)
            wine_binary = Path(self.directory) / wine_dir_name / "bin" / "wine"
            if not wine_binary.exists():
                self.log("Wine binary not found", "error")
                return False

            self.log("Wine binary verified", "success")
            self.update_progress(1.0)
            return True

        except Exception as e:
            self.log(f"Error installing Wine: {e}", "error")
            return False

    def switch_wine_version(self):
        """Switch to a different Wine version - removes current and installs new one"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Switch Wine Version", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is installed
        wine_dir = self.get_wine_dir()
        if not wine_dir.exists():
            self.log(
                "No Wine installation found. Use 'Setup Wine Environment' to install Wine first.",
                "warning",
            )
            QMessageBox.warning(
                self,
                "No Wine Installation",
                "No Wine installation found.\n\n"
                "Please use 'Setup Wine Environment' to install Wine first.",
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Switch Wine Version",
            "This will remove the current Wine installation and install a new version.\n\n"
            "Your Wine prefix and installed applications will NOT be affected.\n"
            "Only the Wine binary will be replaced.\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            self.log("Wine version switch cancelled", "warning")
            return

        # Ask user to choose Wine version
        wine_version = self.show_question_dialog(
            "Choose Wine Version",
            "Which Wine version would you like to install?\n\n"
            "• Wine 11.0 (Recommended) - ElementalWarrior Wine 11.0 with AMD GPU and OpenCL patches. Latest version with best compatibility and performance.\n"
            "• Wine 10.10 - ElementalWarrior Wine 10.10 with AMD GPU and OpenCL patches. Previous stable version.\n"
            "• Wine 9.14 (Legacy) - Legacy version with AMD GPU and OpenCL patches. Fallback option if you encounter issues with newer versions.\n\n"
            "Note: This will replace your current Wine installation.",
            ["Wine 11.0 (Recommended)", "Wine 10.10", "Wine 9.14 (Legacy)"],
        )

        if wine_version == "Wine 11.0 (Recommended)":
            wine_version_choice = "11.0"
        elif wine_version == "Wine 10.10":
            wine_version_choice = "10.10"
        elif wine_version == "Wine 9.14 (Legacy)":
            wine_version_choice = "9.14"
        else:
            self.log("Wine version switch cancelled", "warning")
            return

        # Run the switch in a thread
        threading.Thread(
            target=self._switch_wine_version_thread,
            args=(wine_version_choice,),
            daemon=True,
        ).start()

    def _switch_wine_version_thread(self, wine_version):
        """Thread function to switch Wine version"""
        self.start_operation("Switching Wine Version")

        try:
            # Check if cancelled
            if self.check_cancelled():
                return False

            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Switching Wine Version", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Step 1: Stop Wine processes
            self.update_progress_text("Stopping Wine processes...")
            self.update_progress(0.1)
            self.log("Stopping Wine processes...", "info")
            self.run_command(["wineserver", "-k"], check=False)
            time.sleep(1)  # Give processes time to terminate

            if self.check_cancelled():
                return False

            # Step 2: Remove current Wine installation (not applicable for system Wine)
            wine_dir = self.get_wine_dir()
            if wine_dir and wine_dir.exists():
                self.update_progress_text("Removing current Wine installation...")
                self.update_progress(0.2)
                self.log(f"Removing current Wine installation: {wine_dir}", "info")
                try:
                    if wine_dir.is_symlink():
                        wine_dir.unlink()
                        self.log("Wine symlink removed", "success")
                    else:
                        shutil.rmtree(wine_dir)
                        self.log("Wine directory removed", "success")
                except Exception as e:
                    self.log(f"Error removing Wine directory: {e}", "error")
                    # Try to continue anyway - setup_wine will handle it

            # Also remove any old wine archive files
            wine_archives = list(Path(self.directory).glob("ElementalWarrior*.tar.*"))
            for archive in wine_archives:
                try:
                    archive.unlink()
                    self.log(f"Removed old archive: {archive.name}", "info")
                except Exception:
                    pass

            if self.check_cancelled():
                return False

            # Step 3: Install new Wine version (skip configuration to preserve existing setup)
            self.update_progress_text(f"Installing Wine {wine_version}...")
            self.update_progress(0.3)
            self.log(
                f"\nInstalling Wine version: {wine_version} (preserving existing configuration)...",
                "info",
            )

            # Call _setup_wine_switch which only replaces the binary, no reconfiguration
            # Pass the wine_version parameter to ensure the correct version is downloaded
            success = self._setup_wine_switch(wine_version)

            if not success:
                self.log(f"Failed to install Wine version: {wine_version}", "error")

            if success:
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Wine version switched successfully!", "success")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self.update_progress_text("Wine version switched")
                self.update_progress(1.0)

                # Refresh installation status
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(500, self.check_installation_status)
            else:
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Failed to switch Wine version", "error")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self.update_progress_text("Failed to switch Wine version")

            self.end_operation()
            return success

        except Exception as e:
            self.log(f"Error switching Wine version: {e}", "error")
            self.update_progress_text("Error switching Wine version")
            self.end_operation()
            return False

    def install_winetricks_deps(self):
        """Install winetricks dependencies - wrapper for button"""
        self.install_winetricks_dependencies()

    def install_system_dependencies(self):
        """Install system dependencies"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Installing System Dependencies", "info")

        # Start operation and check for cancellation
        self.start_operation("Installing System Dependencies")
        if self.check_cancelled():
            return
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        threading.Thread(target=self._install_system_deps, daemon=True).start()

    def _install_system_deps(self):
        """Install system dependencies in thread"""
        if self.distro == "pikaos":
            self.log("Using PikaOS dependency installation...", "info")
            success = self.install_pikaos_dependencies()
            if success:
                # Also install .NET SDK if not already installed
                if not self.check_dotnet_sdk():
                    self.log("Installing .NET SDK...", "info")
                    self.install_dotnet_sdk()
            self.log(
                "System dependencies installation completed"
                if success
                else "System dependencies installation failed",
                "success" if success else "error",
            )
            self.end_operation()
            return

        if not self.distro:
            self.detect_distro()

        # Check for distributions that should be directed to PikaOS instead
        if self.distro in ["bazzite"]:
            distro_name = self.format_distro_name()
            message = f"""{distro_name} is not officially supported for optimal Affinity compatibility.

For better support and compatibility, we recommend installing PikaOS - a Debian-based distribution specifically optimized for gaming and compatibility:

https://wiki.pika-os.com/en/home

PikaOS provides:
• Better Wine compatibility
• Gaming-focused optimizations
• Regular updates for Affinity applications
• Debian base with enhanced package management

Would you like to continue with {distro_name} anyway?"""

            reply = self.show_question_dialog(
                f"{distro_name} Not Recommended", message, ["Continue Anyway", "Cancel"]
            )

            if reply == "Cancel":
                self.log(
                    f"Installation cancelled by user due to {distro_name} recommendation",
                    "warning",
                )
                self.end_operation()
                return False

        self.log(f"Installing dependencies for {self.format_distro_name()}...", "info")
        success = self.install_dependencies()

        # After installing main dependencies, check and install .NET SDK if missing
        # (it should be included in install_dependencies, but check anyway)
        if success:
            if not self.check_dotnet_sdk():
                self.log(
                    ".NET SDK not found in installed packages. Installing separately...",
                    "info",
                )
                self.install_dotnet_sdk()
            else:
                self.log(".NET SDK is already installed", "success")

        self.log(
            "System dependencies installation completed"
            if success
            else "System dependencies installation failed",
            "success" if success else "error",
        )
        self.end_operation()
        return success

    def install_winetricks_dependencies(self):
        """Install winetricks dependencies"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Installing Winetricks Dependencies", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Start operation and check for cancellation
        self.start_operation("Installing Winetricks Dependencies")
        if self.check_cancelled():
            return

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please wait for Wine setup to complete.",
                "error",
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before installing winetricks dependencies.",
            )
            self.end_operation()
            return

        threading.Thread(target=self._install_winetricks_deps, daemon=True).start()

    def _install_winetricks_deps(self):
        """Install winetricks dependencies in thread"""
        try:
            if self.check_cancelled():
                return

            # Ensure wine-tkg is available for winetricks
            self.log("Setting up wine-tkg for winetricks...", "info")
            if not self.ensure_wine_tkg():
                self.log(
                    "Failed to setup wine-tkg, continuing with system wine", "warning"
                )

            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            # Prevent winetricks from showing GUI dialogs
            env["WINETRICKS_GUI"] = "0"
            env["DISPLAY"] = env.get(
                "DISPLAY", ":0"
            )  # Ensure display is set but winetricks won't use GUI

            # Use wine-tkg for winetricks if available
            env = self.get_winetricks_env_with_tkg(env)

            components = [
                ("dotnet35sp1", ".NET Framework 3.5 SP1"),
                ("dotnet48", ".NET Framework 4.8"),
                ("corefonts", "Windows Core Fonts"),
                ("vcrun2022", "Visual C++ Redistributables 2022"),
                ("msxml3", "MSXML 3.0"),
                ("msxml6", "MSXML 6.0"),
                ("crypt32", "Cryptographic API 32"),
                ("tahoma", "Tahoma Font"),
                ("renderer=vulkan", "Vulkan Renderer"),
            ]
        except Exception as e:
            self.log(
                f"Error in winetricks dependencies installation: {str(e)}", "error"
            )
            self.log("Please check the logs and try again.", "error")
            self.end_operation()
            return

        self.log(
            "Installing Wine components (this may take several minutes)...", "info"
        )

        total_components = len(components)
        for idx, (component, description) in enumerate(components):
            # Calculate base progress for this component (0.0 to 1.0 across all components)
            base_progress = idx / total_components
            component_progress_range = 1.0 / total_components

            # Update progress label to show current component
            self.update_progress_text(
                f"Installing: {description} ({idx + 1}/{total_components})"
            )

            self.log(
                f"Installing {description} ({component})... [{idx + 1}/{total_components}]",
                "info",
            )
            self.log(
                "  (This may take several minutes - progress will be shown below)",
                "info",
            )

            # Progress callback that updates based on component progress
            def update_component_progress(percent):

                # Update progress label to show current component
                self.update_progress_text(
                    f"Installing: {description} ({idx + 1}/{total_components})"
                )

                self.log(
                    f"Installing {description} ({component})... [{idx + 1}/{total_components}]",
                    "info",
                )
                self.log(
                    "  (This may take several minutes - progress will be shown below)",
                    "info",
                )

                # Progress callback that updates based on component progress
                def update_component_progress(percent):
                    # percent is 0.0-1.0 for this component
                    # Map it to overall progress
                    overall_progress = base_progress + (
                        percent * component_progress_range
                    )
                    self.update_progress(overall_progress)

                # Check for cancellation before starting installation
                if self.check_cancelled():
                    return

                # Use streaming to show progress in real-time
                # Keep --unattended to prevent dialogs, but remove it for verbose output
                # We'll use verbose mode to see progress
                try:
                    success = self.run_command_streaming(
                        [
                            "winetricks",
                            "--unattended",
                            "--verbose",
                            "--force",
                            "--no-isolate",
                            "--optout",
                            component,
                        ],
                        env=env,
                        progress_callback=update_component_progress,
                    )

                    if success and not self.check_cancelled():
                        self.log(f"✓ {description} installed", "success")
                    elif not success and not self.check_cancelled():
                        # If installation failed, try once more with force
                        self.log(
                            f"⚠ {description} installation failed, retrying...",
                            "warning",
                        )
                        time.sleep(2)  # Brief pause before retry

                        self.log(f"Retrying {description} installation...", "info")
                        retry_success = self.run_command_streaming(
                            [
                                "winetricks",
                                "--unattended",
                                "--verbose",
                                "--force",
                                "--no-isolate",
                                "--optout",
                                component,
                            ],
                            env=env,
                            progress_callback=update_component_progress,
                        )

                        # Mark component as complete after retry
                        self.update_progress(base_progress + component_progress_range)

                        if retry_success:
                            self.log(
                                f"✓ {description} installed successfully on retry",
                                "success",
                            )
                        else:
                            # Check if it might already be installed by checking the component
                            if self._check_winetricks_component(
                                component.split("=")[0]
                                if "=" in component
                                else component,
                                self.get_wine_path("wine"),
                                env,
                            ):
                                self.log(
                                    f"✓ {description} appears to already be installed",
                                    "success",
                                )
                            else:
                                self.log(
                                    f"✗ {description} installation failed after retry. You may need to install manually.",
                                    "error",
                                )

                except Exception as e:
                    if not self.check_cancelled():
                        self.log(f"Error during Winetricks installation: {e}", "error")
                finally:
                    # Make sure to end the operation even if there was an error or cancellation
                    if (
                        hasattr(self, "current_operation")
                        and self.current_operation
                        == "Installing Winetricks Dependencies"
                    ):
                        self.end_operation()
                    # Windows 11 compatibility will be set below

            # Set Windows version to 11
            wine_cfg = self.get_wine_path("winecfg")
            self.log("Setting Windows version to 11...", "info")
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            # Apply dark theme
            self.log("Applying Wine dark theme...", "info")
            theme_file = Path(self.directory) / "wine-dark-theme.reg"
            if self.download_file(
                "https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Auxiliary/Other/wine-dark-theme.reg",
                str(theme_file),
                "dark theme",
            ):
                regedit = self.get_wine_path("regedit")
                self.run_command([str(regedit), str(theme_file)], check=False, env=env)
                theme_file.unlink()
                self.log("Dark theme applied", "success")

            self.log("\n✓ Winetricks dependencies installation completed!", "success")
            self.update_progress_text("Ready")
            self.end_operation()

    def install_affinity_settings(self):
        """Install Affinity v3 (Unified) settings files to enable settings saving"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Fix Settings (Affinity v3 only)", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log("Note: This fix applies only to Affinity v3 (Unified).", "info")

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please setup Wine environment first.", "error"
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before installing Affinity v3 settings.\n"
                "Please setup Wine environment first.",
            )
            return

        # Start operation and wrapper thread
        self.start_operation("Install Affinity v3 Settings")
        threading.Thread(
            target=self._install_affinity_settings_entry, daemon=True
        ).start()

    def _install_affinity_settings_thread(self):
        """Install Affinity v3 (Unified) settings in background thread - downloads repo and copies Settings"""
        # Determine Windows username
        # Wine typically uses "Public" as the default username, but check for existing users
        users_dir = Path(self.directory) / "drive_c" / "users"
        username = "Public"  # Default Wine username

        # Check if users directory exists and has other users
        if users_dir.exists():
            # Look for existing user directories (excluding Public, Default, etc.)
            existing_users = [
                d.name
                for d in users_dir.iterdir()
                if d.is_dir()
                and d.name not in ["Public", "Default", "All Users", "Default User"]
            ]
            if existing_users:
                # Use the first existing user, or fall back to Public
                username = existing_users[0]
                self.log(f"Using existing Windows user: {username}", "info")
            else:
                self.log(f"Using default Windows user: {username}", "info")
        else:
            self.log(f"Creating users directory structure for: {username}", "info")
            users_dir.mkdir(parents=True, exist_ok=True)

        # Create temp directory for cloning/downloading
        temp_dir = Path(self.directory) / ".temp_settings"
        if temp_dir.exists():
            self.log("Cleaning up existing temp directory...", "info")
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                self.log(f"Warning: Could not remove existing temp dir: {e}", "warning")
        temp_dir.mkdir(exist_ok=True)

        # Download the repository as a zip file
        self.update_progress_text("Downloading Settings from repository...")
        self.update_progress(0.1)
        self.log("Downloading Settings from GitHub repository...", "info")
        repo_zip = temp_dir / "AffinityOnLinux.zip"
        repo_url = (
            "https://github.com/seapear/AffinityOnLinux/archive/refs/heads/main.zip"
        )

        if not self.download_file(repo_url, str(repo_zip), "Settings repository"):
            self.log("Failed to download Settings repository", "error")
            self.log(f"  URL: {repo_url}", "error")
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            return

        # Verify the zip file was downloaded
        if not repo_zip.exists() or repo_zip.stat().st_size == 0:
            self.log("Downloaded zip file is missing or empty", "error")
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            return

        self.log(
            f"Downloaded zip file size: {repo_zip.stat().st_size / 1024 / 1024:.2f} MB",
            "info",
        )

        # Extract the zip file
        self.update_progress_text("Extracting Settings repository...")
        self.update_progress(0.3)
        self.log("Extracting Settings repository...", "info")
        try:
            if self.check_command("7z"):
                success, stdout, stderr = self.run_command(
                    ["7z", "x", str(repo_zip), f"-o{temp_dir}", "-y"]
                )
                if not success:
                    self.log(f"7z extraction failed: {stderr}", "error")
                    raise Exception("7z extraction failed")
                self.log("Extraction completed with 7z", "success")
            elif self.check_command("unzip"):
                with zipfile.ZipFile(repo_zip, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)
                self.log("Extraction completed with unzip", "success")
            else:
                self.log("Neither 7z nor unzip available for extraction", "error")
                self.log(
                    "Please install 7z or unzip to extract the repository", "error"
                )
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            # Find the extracted directory (usually AffinityOnLinux-main)
            extracted_dirs = list(temp_dir.glob("AffinityOnLinux-*"))
            self.log(
                f"Found {len(extracted_dirs)} extracted director{'y' if len(extracted_dirs) == 1 else 'ies'}",
                "info",
            )

            extracted_dir = extracted_dirs[0] if extracted_dirs else None
            if not extracted_dir:
                self.log("Could not find extracted repository directory", "error")
                self.log(
                    f"Contents of temp_dir: {[d.name for d in temp_dir.iterdir()]}",
                    "error",
                )
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            self.log(f"Using extracted directory: {extracted_dir.name}", "info")

            # Check if Auxiliary directory exists
            auxiliary_dir = extracted_dir / "Auxiliary"
            if not auxiliary_dir.exists():
                self.log("Auxiliary directory not found in repository", "error")
                self.log(
                    f"Contents of extracted directory: {[d.name for d in extracted_dir.iterdir()]}",
                    "error",
                )
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            settings_dir = auxiliary_dir / "Settings"
            if not settings_dir.exists():
                self.log("Settings directory not found in Auxiliary", "error")
                self.log(
                    f"Contents of Auxiliary: {[d.name for d in auxiliary_dir.iterdir()]}",
                    "error",
                )
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            # List what's in the Settings directory
            settings_contents = [d.name for d in settings_dir.iterdir() if d.is_dir()]
            self.log(f"Found Settings folders: {settings_contents}", "info")

            # Source Settings directory path - For Affinity v3 (Unified), use 3.0
            # $APP would be "Affinity" and version is 3.0
            # So the source should be: Auxiliary/Settings/Affinity/3.0/Settings
            self.update_progress_text("Locating Settings files...")
            self.update_progress(0.5)
            settings_source_dirs = [
                settings_dir / "Affinity" / "3.0" / "Settings",  # Affinity v3 uses 3.0
                settings_dir / "Affinity" / "Settings",
                settings_dir / "Unified" / "3.0" / "Settings",
                settings_dir / "Unified" / "Settings",
            ]

            settings_source = None
            for source_dir in settings_source_dirs:
                if source_dir.exists():
                    files = list(source_dir.iterdir())
                    if files:
                        settings_source = source_dir
                        self.log(
                            f"Found settings at: {source_dir.relative_to(extracted_dir)}",
                            "success",
                        )
                        self.log(f"  Contains {len(files)} file(s)/folder(s)", "info")
                        break

            if not settings_source:
                self.log("Settings directory not found in repository", "error")
                self.log("Tried paths:", "error")
                for path in settings_source_dirs:
                    self.log(
                        f"  - {path.relative_to(extracted_dir)}: {'exists' if path.exists() else 'not found'}",
                        "error",
                    )

                # List what's actually in Settings/Affinity if it exists
                affinity_settings = settings_dir / "Affinity"
                if affinity_settings.exists():
                    self.log(
                        f"Contents of Settings/Affinity: {[d.name for d in affinity_settings.iterdir()]}",
                        "info",
                    )

                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            # Target directory in Wine prefix
            # Based on Settings.md: mv $APP/3.0/Settings drive_c/users/$USERNAME/AppData/Roaming/Affinity/
            # For Affinity v3, this means: Affinity/3.0/Settings -> AppData/Roaming/Affinity/Affinity/3.0/Settings
            affinity_appdata = users_dir / username / "AppData" / "Roaming" / "Affinity"

            # Check what version folder Affinity v3 actually uses by looking at existing structure
            affinity_dir = affinity_appdata / "Affinity"
            version_folder = None
            if affinity_dir.exists():
                existing_versions = [
                    d.name for d in affinity_dir.iterdir() if d.is_dir()
                ]
                if existing_versions:
                    # Prefer 3.0 for Affinity v3
                    if "3.0" in existing_versions:
                        version_folder = "3.0"
                    elif "2.0" in existing_versions:
                        version_folder = "2.0"
                    else:
                        # Use the first one found (sorted)
                        version_folder = sorted(existing_versions)[0]
                    self.log(
                        f"Found existing Affinity version folder: {version_folder}",
                        "info",
                    )

            # If no existing version folder, use 3.0 for Affinity v3
            if not version_folder:
                # Try to detect from source path
                source_parts = settings_source.parts
                if "3.0" in source_parts:
                    version_folder = "3.0"
                elif "2.0" in source_parts:
                    version_folder = "2.0"
                else:
                    version_folder = "3.0"  # Default to 3.0 for Affinity v3
                self.log(
                    f"Using version folder: {version_folder} (Affinity v3 uses 3.0)",
                    "info",
                )

            # Target path: AppData/Roaming/Affinity/Affinity/3.0/Settings (for v3)
            target_dir = affinity_appdata / "Affinity" / version_folder / "Settings"

            # Remove existing settings if they exist (to force fresh copy)
            if target_dir.exists():
                self.log(f"Removing existing settings from: {target_dir}", "info")
                try:
                    shutil.rmtree(target_dir)
                    self.log("Old settings removed", "success")
                except Exception as e:
                    self.log(
                        f"Warning: Could not fully remove old settings: {e}", "warning"
                    )

            # Copy settings from source to target
            self.update_progress_text("Copying Settings files...")
            self.update_progress(0.7)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"Copying settings from repository to Wine prefix...", "info")
            self.log(f"  From: {settings_source}", "info")
            self.log(f"  To: {target_dir}", "info")

            # Copy with metadata preservation
            shutil.copytree(settings_source, target_dir, dirs_exist_ok=True)
            self.update_progress(0.9)
            self.log(f"Settings copied successfully to: {target_dir}", "success")

            # Verify the copy
            copied_files = list(target_dir.rglob("*"))
            source_files = list(settings_source.rglob("*"))
            self.log(
                f"Copied {len(copied_files)} file(s)/folder(s) (source had {len(source_files)})",
                "success",
            )

            # List some of the copied files for verification
            xml_files = list(target_dir.rglob("*.xml"))
            if xml_files:
                self.log(f"Found {len(xml_files)} XML file(s) in settings", "info")
                for xml_file in xml_files[:5]:  # Show first 5
                    self.log(f"  - {xml_file.relative_to(target_dir)}", "info")

            # Set permissions (make sure files are readable)
            try:
                for root, dirs, files in os.walk(target_dir):
                    for d in dirs:
                        os.chmod(os.path.join(root, d), 0o755)
                    for f in files:
                        os.chmod(os.path.join(root, f), 0o644)
                self.log("File permissions set correctly", "success")
            except Exception as e:
                self.log(f"Note: Could not set permissions: {e}", "warning")

            # Clean up temp files
            try:
                shutil.rmtree(temp_dir)
                self.log("Temp files cleaned up", "info")
            except Exception as e:
                self.log(f"Note: Could not clean up temp files: {e}", "warning")

            self.update_progress(1.0)
            self.update_progress_text("Settings installation complete!")
            self.log("\n✓ Affinity v3 settings installation completed!", "success")
            self.log(
                "Settings files have been installed for Affinity v3 (Unified).", "info"
            )

        except Exception as e:
            import traceback

            self.log(f"Error installing settings: {e}", "error")
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            # Clean up on error
            try:
                shutil.rmtree(temp_dir)
                repo_zip.unlink(missing_ok=True)
            except:
                pass

    def _check_winetricks_component(self, component, wine, env):
        """Check if a winetricks component is installed"""
        try:
            # Different checks for different components
            if component == "dotnet35sp1" or component == "dotnet35":
                # Check for .NET 3.5 in registry (dotnet35sp1 installs .NET 3.5 SP1)
                success, stdout, _ = self.run_command(
                    [
                        str(wine),
                        "reg",
                        "query",
                        "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5",
                        "/v",
                        "Install",
                    ],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success and stdout:
                    # Check if Install value is 1
                    if "0x1" in stdout or "REG_DWORD" in stdout:
                        return True
            elif component == "dotnet48":
                # Check for .NET 4.8 in registry
                success, stdout, _ = self.run_command(
                    [
                        str(wine),
                        "reg",
                        "query",
                        "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v4\\Full",
                        "/v",
                        "Release",
                    ],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success and stdout:
                    # .NET 4.8 has release number 528040 or higher
                    match = re.search(r"0x([0-9a-fA-F]+)", stdout)
                    if match:
                        release = int(match.group(1), 16)
                        if release >= 528040:  # .NET 4.8
                            return True
            elif component == "corefonts":
                # Check if core fonts directory exists
                fonts_dir = Path(self.directory) / "drive_c" / "windows" / "Fonts"
                if fonts_dir.exists():
                    # Check for some common core fonts
                    core_fonts = ["arial.ttf", "times.ttf", "courier.ttf", "tahoma.ttf"]
                    for font in core_fonts:
                        if (fonts_dir / font).exists():
                            return True
            elif component == "vcrun2022":
                # Check for Visual C++ 2022 redistributables
                vcrun_paths = [
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "system32"
                    / "vcruntime140.dll",
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "syswow64"
                    / "vcruntime140.dll",
                ]
                for vcrun_path in vcrun_paths:
                    if vcrun_path.exists():
                        return True
            elif component == "msxml3":
                # Check for MSXML3
                msxml3_path = (
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "system32"
                    / "msxml3.dll"
                )
                if msxml3_path.exists():
                    return True
            elif component == "msxml6":
                # Check for MSXML6
                msxml6_path = (
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "system32"
                    / "msxml6.dll"
                )
                if msxml6_path.exists():
                    return True
            elif component == "crypt32":
                # Check for Cryptographic API 32 (crypt32.dll)
                crypt32_paths = [
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "system32"
                    / "crypt32.dll",
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "syswow64"
                    / "crypt32.dll",
                ]
                for crypt32_path in crypt32_paths:
                    if crypt32_path.exists():
                        return True
        except Exception:
            pass

        return False

    def check_webview2_installed(self):
        """Check if WebView2 Runtime is already installed (fast check - file paths only)"""
        # Fast check: only check file paths, skip slow registry query
        webview2_paths = [
            Path(self.directory)
            / "drive_c"
            / "Program Files (x86)"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
        ]

        for webview2_path in webview2_paths:
            if webview2_path.exists():
                # Check if msedgewebview2.exe exists
                msedgewebview2_exe = webview2_path / "msedgewebview2.exe"
                if msedgewebview2_exe.exists():
                    return True

        # If file check fails, do a registry check (only if file check failed)
        # Skip registry check to make it faster - file check is usually sufficient
        # Registry check can be slow and may hang, so we skip it for speed
        return False

        return False

    def install_webview2_runtime(self):
        """Install Microsoft Edge WebView2 Runtime for Affinity v3 (Unified)"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Installing Microsoft Edge WebView2 Runtime (Affinity v3)", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if system Wine is available (WebView2 uses system wine, not patched wine)
        if not shutil.which("wine"):
            self.log(
                "System Wine is not installed. Please install Wine first.", "error"
            )
            QMessageBox.warning(
                self,
                "Wine Not Installed",
                "System Wine is required for WebView2 Runtime installation.\n\n"
                "Please install Wine using your distribution's package manager:\n"
                "  • Arch/Artix/CachyOS/EndeavourOS/XeroLinux: sudo pacman -S wine\n"
                "  • Fedora/Nobara: sudo dnf install wine\n"
                "  • PikaOS: sudo apt install wine",
            )
            return

        # Start operation and wrapper thread
        self.start_operation("Install WebView2 Runtime")
        threading.Thread(
            target=self._install_webview2_runtime_entry, daemon=True
        ).start()

    def _install_webview2_runtime_entry(self):
        """Wrapper to install WebView2 and end the operation when invoked from the button."""
        try:
            self._install_webview2_runtime_thread()
        finally:
            self.end_operation()

    def _install_webview2_runtime_thread(self):
        """Install Microsoft Edge WebView2 Runtime in background thread"""
        # Check if system Wine is available (WebView2 uses system wine, not patched wine)
        if not shutil.which("wine"):
            self.log(
                "System Wine is not installed. Please install Wine first.", "error"
            )
            self.log(
                "You can install Wine using your distribution's package manager.",
                "info",
            )
            return False

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        # Use system wine tools for WebView2 (not patched wine)
        wine_cfg = "winecfg"
        regedit = "regedit"
        wine = "wine"

        self.log(
            f"Using system Wine for WebView2 installation (WINEPREFIX={self.directory})",
            "info",
        )

        # Check if WebView2 Runtime is already installed
        self.log("Checking if WebView2 Runtime is already installed...", "info")
        webview2_installed = False

        # Check for WebView2 installation directory
        webview2_paths = [
            Path(self.directory)
            / "drive_c"
            / "Program Files (x86)"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
        ]

        for webview2_path in webview2_paths:
            if webview2_path.exists():
                # Check if msedgewebview2.exe exists
                msedgewebview2_exe = webview2_path / "msedgewebview2.exe"
                if msedgewebview2_exe.exists():
                    webview2_installed = True
                    self.log(f"WebView2 Runtime found at: {webview2_path}", "success")
                    break

        # Also check registry for WebView2 installation
        if not webview2_installed:
            try:
                success, stdout, _ = self.run_command(
                    [
                        str(wine),
                        "reg",
                        "query",
                        "HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
                    ],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success:
                    webview2_installed = True
                    self.log("WebView2 Runtime found in registry", "success")
            except Exception:
                pass

        if webview2_installed:
            self.log(
                "WebView2 Runtime is already installed. Skipping installation.", "info"
            )
            self.log("Verifying configuration...", "info")

            # Still configure the compatibility settings even if already installed
            # Step 1: Disable Microsoft Edge Update services (if not already done)
            self.log("Ensuring Edge Update services are disabled...", "info")
            disable_edge_update_reg = Path(self.directory) / "disable-edge-update.reg"
            with open(disable_edge_update_reg, "w") as f:
                f.write("Windows Registry Editor Version 5.00\n\n")
                f.write(
                    "[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\edgeupdate]\n"
                )
                f.write('"Start"=dword:00000004\n\n')
                f.write(
                    "[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\edgeupdatem]\n"
                )
                f.write('"Start"=dword:00000004\n')

            self.run_command(
                [str(regedit), str(disable_edge_update_reg)], check=False, env=env
            )
            disable_edge_update_reg.unlink()

            # Step 2: Set msedgewebview2.exe to Windows 7 compatibility (if not already set)
            self.log(
                "Ensuring msedgewebview2.exe Windows 7 compatibility is set...", "info"
            )
            webview2_win7_reg = Path(self.directory) / "webview2-win7-cap.reg"
            with open(webview2_win7_reg, "w") as f:
                f.write("Windows Registry Editor Version 5.00\n\n")
                f.write("[HKEY_CURRENT_USER\\Software\\Wine\\AppDefaults]\n\n")
                f.write(
                    "[HKEY_CURRENT_USER\\Software\\Wine\\AppDefaults\\msedgewebview2.exe]\n"
                )
                f.write('"Version"="win7"\n')

            self.run_command(
                [str(regedit), str(webview2_win7_reg)], check=False, env=env
            )
            webview2_win7_reg.unlink()

            self.log("\n✓ WebView2 Runtime configuration verified!", "success")
            self.log("WebView2 Runtime is installed and configured correctly.", "info")
            return True

        # WebView2 not found, proceed with installation
        self.log("WebView2 Runtime not found. Proceeding with installation...", "info")

        try:
            # Step 1: Set Windows 11 compatibility mode
            self.log("Setting Windows 11 compatibility mode...", "info")
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)
            self.log("Windows 11 compatibility mode set", "success")

            # Step 2: Download Microsoft Edge WebView2 Runtime
            self.log("Downloading Microsoft Edge WebView2 Runtime...", "info")
            webview2_url = "https://github.com/ryzendew/AffinityOnLinux/releases/download/10.4-Wine-Affinity/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
            webview2_file = (
                Path(self.directory) / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
            )

            if not self.download_file(
                webview2_url, str(webview2_file), "WebView2 Runtime"
            ):
                self.log("Failed to download WebView2 Runtime", "error")
                return False

            self.log("WebView2 Runtime downloaded", "success")

            # Step 3: Install WebView2 Runtime using system wine (like Affinity v3)
            self.log("Installing Microsoft Edge WebView2 Runtime...", "info")
            self.log("This may take a few minutes...", "info")
            self.log("Using system Wine for WebView2 installation", "info")
            env["WINEDEBUG"] = "-all"

            # Use system wine for WebView2 installer (like Affinity v3)
            # Use the installer capture method which has better timeout handling
            success = self._run_installer_and_capture(
                webview2_file, env, label="WebView2 installer"
            )
            if not success:
                self.log(
                    "WebView2 installer may have completed despite non-zero exit code",
                    "warning",
                )

            # Wait a moment for files to be written
            time.sleep(3)
            self.log("WebView2 Runtime installation completed", "success")

            # Step 4: Disable Microsoft Edge Update services
            self.log("Disabling Microsoft Edge Update services...", "info")
            disable_edge_update_reg = Path(self.directory) / "disable-edge-update.reg"
            with open(disable_edge_update_reg, "w") as f:
                f.write("Windows Registry Editor Version 5.00\n\n")
                f.write(
                    "[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\edgeupdate]\n"
                )
                f.write('"Start"=dword:00000004\n\n')
                f.write(
                    "[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\edgeupdatem]\n"
                )
                f.write('"Start"=dword:00000004\n')

            self.run_command(
                [str(regedit), str(disable_edge_update_reg)], check=False, env=env
            )
            disable_edge_update_reg.unlink()
            self.log("Edge Update services disabled", "success")

            # Step 5: Set msedgewebview2.exe to Windows 7 compatibility
            self.log("Setting msedgewebview2.exe to Windows 7 compatibility...", "info")
            webview2_win7_reg = Path(self.directory) / "webview2-win7-cap.reg"
            with open(webview2_win7_reg, "w") as f:
                f.write("Windows Registry Editor Version 5.00\n\n")
                f.write("[HKEY_CURRENT_USER\\Software\\Wine\\AppDefaults]\n\n")
                f.write(
                    "[HKEY_CURRENT_USER\\Software\\Wine\\AppDefaults\\msedgewebview2.exe]\n"
                )
                f.write('"Version"="win7"\n')

            self.run_command(
                [str(regedit), str(webview2_win7_reg)], check=False, env=env
            )
            webview2_win7_reg.unlink()
            self.log("msedgewebview2.exe Windows 7 compatibility set", "success")

            # Clean up installer file
            if webview2_file.exists():
                webview2_file.unlink()
                self.log("WebView2 installer file removed", "success")

            self.log(
                "\n✓ Microsoft Edge WebView2 Runtime installation completed!", "success"
            )
            self.log("WebView2 Runtime has been installed for Affinity v3.", "info")
            self.log("Help > View Help should now work in Affinity v3.", "info")
            return True

        except Exception as e:
            if not self.check_cancelled():
                self.log(f"Error installing WebView2 Runtime: {e}", "error")
            # Try to restore Windows 11 compatibility even if something failed
            try:
                self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)
            except:
                pass
            return False

    def _install_affinity_settings_entry(self):
        """Wrapper to install Affinity settings and end the operation when invoked from the button."""
        try:
            self._install_affinity_settings_thread()
        finally:
            self.end_operation()

    def _install_affinity_settings_thread(self):
        """Install Affinity v3 (Unified) settings in background thread - downloads repo and copies Settings"""
        try:
            # Determine Windows username
            # Wine typically uses "Public" as the default username, but check for existing users
            users_dir = Path(self.directory) / "drive_c" / "users"
            username = "Public"  # Default Wine username

            # Check if users directory exists and has other users
            if users_dir.exists():
                # Look for existing user directories (excluding Public, Default, etc.)
                existing_users = [
                    d.name
                    for d in users_dir.iterdir()
                    if d.is_dir()
                    and d.name not in ["Public", "Default", "All Users", "Default User"]
                ]
                if existing_users:
                    # Use the first existing user, or fall back to Public
                    username = existing_users[0]
                    self.log(f"Using existing Windows user: {username}", "info")
                else:
                    self.log(f"Using default Windows user: {username}", "info")
            else:
                self.log(f"Creating users directory structure for: {username}", "info")
                users_dir.mkdir(parents=True, exist_ok=True)

            # Create temp directory for cloning/downloading
            temp_dir = Path(self.directory) / ".temp_settings"
            if temp_dir.exists():
                self.log("Cleaning up existing temp directory...", "info")
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove existing temp dir: {e}", "warning"
                    )
            temp_dir.mkdir(exist_ok=True)

            # Download the repository as a zip file
            self.update_progress_text("Downloading Settings from repository...")
            self.update_progress(0.1)
            self.log("Downloading Settings from GitHub repository...", "info")
            repo_zip = temp_dir / "AffinityOnLinux.zip"
            repo_url = (
                "https://github.com/seapear/AffinityOnLinux/archive/refs/heads/main.zip"
            )

            if not self.download_file(repo_url, str(repo_zip), "Settings repository"):
                self.log("Failed to download Settings repository", "error")
                self.log(f"  URL: {repo_url}", "error")
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            # Verify the zip file was downloaded
            if not repo_zip.exists() or repo_zip.stat().st_size == 0:
                self.log("Downloaded zip file is missing or empty", "error")
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            self.log(
                f"Downloaded zip file size: {repo_zip.stat().st_size / 1024 / 1024:.2f} MB",
                "info",
            )

            # Extract the zip file
            self.update_progress_text("Extracting Settings repository...")
            self.update_progress(0.3)
            self.log("Extracting Settings repository...", "info")
            try:
                if self.check_command("7z"):
                    success, stdout, stderr = self.run_command(
                        ["7z", "x", str(repo_zip), f"-o{temp_dir}", "-y"]
                    )
                    if not success:
                        self.log(f"7z extraction failed: {stderr}", "error")
                        raise Exception("7z extraction failed")
                    self.log("Extraction completed with 7z", "success")
                elif self.check_command("unzip"):
                    with zipfile.ZipFile(repo_zip, "r") as zip_ref:
                        zip_ref.extractall(temp_dir)
                    self.log("Extraction completed with unzip", "success")
                else:
                    self.log("Neither 7z nor unzip available for extraction", "error")
                    self.log(
                        "Please install 7z or unzip to extract the repository", "error"
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                # Find the extracted directory (usually AffinityOnLinux-main)
                extracted_dirs = list(temp_dir.glob("AffinityOnLinux-*"))
                self.log(
                    f"Found {len(extracted_dirs)} extracted director{'y' if len(extracted_dirs) == 1 else 'ies'}",
                    "info",
                )

                extracted_dir = extracted_dirs[0] if extracted_dirs else None
                if not extracted_dir:
                    self.log("Could not find extracted repository directory", "error")
                    self.log(
                        f"Contents of temp_dir: {[d.name for d in temp_dir.iterdir()]}",
                        "error",
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                self.log(f"Using extracted directory: {extracted_dir.name}", "info")

                # Check if Auxiliary directory exists
                auxiliary_dir = extracted_dir / "Auxiliary"
                if not auxiliary_dir.exists():
                    self.log("Auxiliary directory not found in repository", "error")
                    self.log(
                        f"Contents of extracted directory: {[d.name for d in extracted_dir.iterdir()]}",
                        "error",
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                settings_dir = auxiliary_dir / "Settings"
                if not settings_dir.exists():
                    self.log("Settings directory not found in Auxiliary", "error")
                    self.log(
                        f"Contents of Auxiliary: {[d.name for d in auxiliary_dir.iterdir()]}",
                        "error",
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                # List what's in the Settings directory
                settings_contents = [
                    d.name for d in settings_dir.iterdir() if d.is_dir()
                ]
                self.log(f"Found Settings folders: {settings_contents}", "info")

                # Source Settings directory path - For Affinity v3 (Unified), use 3.0
                # $APP would be "Affinity" and version is 3.0
                # So the source should be: Auxiliary/Settings/Affinity/3.0/Settings
                self.update_progress_text("Locating Settings files...")
                self.update_progress(0.5)
                settings_source_dirs = [
                    settings_dir
                    / "Affinity"
                    / "3.0"
                    / "Settings",  # Affinity v3 uses 3.0
                    settings_dir / "Affinity" / "Settings",
                    settings_dir / "Unified" / "3.0" / "Settings",
                    settings_dir / "Unified" / "Settings",
                ]

                settings_source = None
                for source_dir in settings_source_dirs:
                    if source_dir.exists():
                        files = list(source_dir.iterdir())
                        if files:
                            settings_source = source_dir
                            self.log(
                                f"Found settings at: {source_dir.relative_to(extracted_dir)}",
                                "success",
                            )
                            self.log(
                                f"  Contains {len(files)} file(s)/folder(s)", "info"
                            )
                            break

                if not settings_source:
                    self.log("Settings directory not found in repository", "error")
                    self.log("Tried paths:", "error")
                    for path in settings_source_dirs:
                        self.log(
                            f"  - {path.relative_to(extracted_dir)}: {'exists' if path.exists() else 'not found'}",
                            "error",
                        )

                    # List what's actually in Settings/Affinity if it exists
                    affinity_settings = settings_dir / "Affinity"
                    if affinity_settings.exists():
                        self.log(
                            f"Contents of Settings/Affinity: {[d.name for d in affinity_settings.iterdir()]}",
                            "info",
                        )

                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                # Target directory in Wine prefix
                # Based on Settings.md: mv $APP/3.0/Settings drive_c/users/$USERNAME/AppData/Roaming/Affinity/
                # For Affinity v3, this means: Affinity/3.0/Settings -> AppData/Roaming/Affinity/Affinity/3.0/Settings
                affinity_appdata = (
                    users_dir / username / "AppData" / "Roaming" / "Affinity"
                )

                # Check what version folder Affinity v3 actually uses by looking at existing structure
                affinity_dir = affinity_appdata / "Affinity"
                version_folder = None
                if affinity_dir.exists():
                    existing_versions = [
                        d.name for d in affinity_dir.iterdir() if d.is_dir()
                    ]
                    if existing_versions:
                        # Prefer 3.0 for Affinity v3
                        if "3.0" in existing_versions:
                            version_folder = "3.0"
                        elif "2.0" in existing_versions:
                            version_folder = "2.0"
                        else:
                            # Use the first one found (sorted)
                            version_folder = sorted(existing_versions)[0]
                        self.log(
                            f"Found existing Affinity version folder: {version_folder}",
                            "info",
                        )

                # If no existing version folder, use 3.0 for Affinity v3
                if not version_folder:
                    # Try to detect from source path
                    source_parts = settings_source.parts
                    if "3.0" in source_parts:
                        version_folder = "3.0"
                    elif "2.0" in source_parts:
                        version_folder = "2.0"
                    else:
                        version_folder = "3.0"  # Default to 3.0 for Affinity v3
                    self.log(
                        f"Using version folder: {version_folder} (Affinity v3 uses 3.0)",
                        "info",
                    )

                # Target path: AppData/Roaming/Affinity/Affinity/3.0/Settings (for v3)
                target_dir = affinity_appdata / "Affinity" / version_folder / "Settings"

                # Remove existing settings if they exist (to force fresh copy)
                if target_dir.exists():
                    self.log(f"Removing existing settings from: {target_dir}", "info")
                    try:
                        shutil.rmtree(target_dir)
                        self.log("Old settings removed", "success")
                    except Exception as e:
                        self.log(
                            f"Warning: Could not fully remove old settings: {e}",
                            "warning",
                        )

                # Copy settings from source to target
                self.update_progress_text("Copying Settings files...")
                self.update_progress(0.7)
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                self.log(f"Copying settings from repository to Wine prefix...", "info")
                self.log(f"  From: {settings_source}", "info")
                self.log(f"  To: {target_dir}", "info")

                # Copy with metadata preservation
                shutil.copytree(settings_source, target_dir, dirs_exist_ok=True)
                self.update_progress(0.9)
                self.log(f"Settings copied successfully to: {target_dir}", "success")

                # Verify the copy
                copied_files = list(target_dir.rglob("*"))
                source_files = list(settings_source.rglob("*"))
                self.log(
                    f"Copied {len(copied_files)} file(s)/folder(s) (source had {len(source_files)})",
                    "success",
                )

                # List some of the copied files for verification
                xml_files = list(target_dir.rglob("*.xml"))
                if xml_files:
                    self.log(f"Found {len(xml_files)} XML file(s) in settings", "info")
                    for xml_file in xml_files[:5]:  # Show first 5
                        self.log(f"  - {xml_file.relative_to(target_dir)}", "info")

                # Set permissions (make sure files are readable)
                try:
                    for root, dirs, files in os.walk(target_dir):
                        for d in dirs:
                            os.chmod(os.path.join(root, d), 0o755)
                        for f in files:
                            os.chmod(os.path.join(root, f), 0o644)
                    self.log("File permissions set correctly", "success")
                except Exception as e:
                    self.log(f"Note: Could not set permissions: {e}", "warning")

                # Clean up temp files
                try:
                    shutil.rmtree(temp_dir)
                    self.log("Temp files cleaned up", "info")
                except Exception as e:
                    self.log(f"Note: Could not clean up temp files: {e}", "warning")

                self.update_progress(1.0)
                self.update_progress_text("Settings installation complete!")
                self.log("\n✓ Affinity v3 settings installation completed!", "success")
                self.log(
                    "Settings files have been installed for Affinity v3 (Unified).",
                    "info",
                )

            except Exception as e:
                import traceback

                self.log(f"Error installing settings: {e}", "error")
                self.log(f"Traceback: {traceback.format_exc()}", "error")
            try:
                shutil.rmtree(temp_dir)
                repo_zip.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as e:
            import traceback

            self.log(f"Error installing settings: {e}", "error")
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            # Clean up on error
            try:
                shutil.rmtree(temp_dir)
                repo_zip.unlink(missing_ok=True)
            except:
                pass

    def install_from_file(self):
        """Install from file manager - custom .exe file"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Custom Installer from File Manager", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please wait for Wine setup to complete.",
                "error",
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before installing applications.\n"
                "Please wait for the initialization to finish.",
            )
            return

        # Open file dialog to select .exe
        self.log("Please select the installer .exe file...", "info")
        installer_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Installer (.exe)",
            "",
            "Executable files (*.exe);;All files (*.*)",
        )

        if not installer_path:
            self.log("Installation cancelled.", "warning")
            return

        # Detect app name from filename - check multiple patterns
        filename_lower = Path(installer_path).name.lower()
        filename_no_spaces = (
            filename_lower.replace(" ", "").replace("-", "").replace("_", "")
        )
        app_name = None

        # Check various patterns that might be in Affinity installer filenames
        if "photo" in filename_lower or "photo" in filename_no_spaces:
            app_name = "Photo"
            self.log(
                f"Detected: Affinity Photo (from filename: {Path(installer_path).name})",
                "info",
            )
        elif "designer" in filename_lower or "designer" in filename_no_spaces:
            app_name = "Designer"
            self.log(
                f"Detected: Affinity Designer (from filename: {Path(installer_path).name})",
                "info",
            )
        elif "publisher" in filename_lower or "publisher" in filename_no_spaces:
            app_name = "Publisher"
            self.log(
                f"Detected: Affinity Publisher (from filename: {Path(installer_path).name})",
                "info",
            )
        elif (
            ("affinity" in filename_lower or "affinity" in filename_no_spaces)
            and ("x64" in filename_lower or "x64" in filename_no_spaces)
            and "photo" not in filename_lower
            and "designer" not in filename_lower
            and "publisher" not in filename_lower
        ):
            app_name = "Add"
            self.log(
                f"Detected: Affinity (Unified) v3 (from filename: {Path(installer_path).name})",
                "info",
            )
        else:
            self.log(
                f"Could not detect Affinity app from filename: {Path(installer_path).name}",
                "warning",
            )
            self.log(
                "Desktop entry will not be created automatically for non-Affinity apps.",
                "info",
            )

        if app_name:
            self.log(f"Will automatically create desktop entry for {app_name}", "info")

        # Start operation and installation
        self.start_operation("Custom Installation")
        threading.Thread(
            target=self._run_custom_installation_entry,
            args=(installer_path, app_name),
            daemon=True,
        ).start()

    def _run_custom_installation_entry(self, installer_path, app_name):
        """Wrapper: run custom installation and always end operation."""
        try:
            self.run_custom_installation(installer_path, app_name)
        finally:
            self.end_operation()

    def run_custom_installation(self, installer_path, app_name):
        """Run custom installation process"""
        try:
            self.log(f"Selected installer: {installer_path}", "success")

            # Copy installer with sanitized filename (remove spaces)
            original_filename = Path(installer_path).name
            sanitized_filename = self.sanitize_filename(original_filename)
            installer_file = Path(self.directory) / sanitized_filename
            shutil.copy2(installer_path, installer_file)
            self.log(
                f"Installer {original_filename} copied to Wine prefix: {installer_file} (WINEPREFIX={self.directory})",
                "success",
            )

            # Set Windows version
            # Use regular Wine for all installations (wine-tkg is only for winetricks)
            wine_cfg = self.get_wine_path("winecfg")
            wine = self.get_wine_path("wine")

            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            # Run installer
            env["WINEDEBUG"] = "-all"
            self.log("Launching installer with custom Wine...", "info")
            self.log("Follow the installation wizard in the window that opens.", "info")
            self.log("Click 'No' if you encounter any errors.", "warning")

            # Run installer and wait until it finishes, capturing logs (with fallback)
            success = self._run_installer_and_capture(
                installer_file, env, label="installer"
            )
            if not success and not self.check_cancelled():
                self.log("Installer process exited with a non-zero status", "warning")
            else:
                self.log("Installer succes.")
            # Clean up installer
            # if installer_file.exists():
            #     installer_file.unlink()
            # self.log("Installer file removed", "success")

            # Restore WinMetadata (only needed for Wine 9.14 and 10.10, not 11.0+)
            wine_version = self.get_current_wine_version()
            if wine_version in ["9.14", "10.10"]:
                self.restore_winmetadata()
            else:
                self.log(
                    "Skipping WinMetadata restore for Wine 11.0+ (not needed)", "info"
                )

            # Set up wintypes.dll and Wine overrides for Affinity apps (v2 and v3) - only for Wine < 11.0
            if app_name in ["Photo", "Designer", "Publisher", "Add"]:
                wine_version = self.get_current_wine_version()
                if wine_version in ["9.14", "10.10"]:
                    self.log("Setting up wintypes.dll and Wine overrides...", "info")
                    # Set up DLL override for wintypes.dll
                    self.setup_wintypes_dll_override()
                    # Copy wintypes.dll for the installed app
                    self.setup_wintypes_dll(app_name)
                else:
                    self.log(
                        "Skipping wintypes.dll setup for Wine 11.0+ (not needed)",
                        "info",
                    )

            # If it's an Affinity app, automatically create desktop entry and configure OpenCL
            if app_name in ["Photo", "Designer", "Publisher"]:
                self.log(f"Detected Affinity app: {app_name}, configuring...", "info")

                # Wait a bit more to ensure installation is fully complete
                time.sleep(2)

                # Configure OpenCL for Affinity apps (if enabled)
                if self.is_opencl_enabled():
                    self.configure_opencl(app_name)

                # Verify app path exists before creating desktop entry
                app_names = {
                    "Photo": ("Photo", "Photo.exe", "Photo 2"),
                    "Designer": ("Designer", "Designer.exe", "Designer 2"),
                    "Publisher": ("Publisher", "Publisher.exe", "Publisher 2"),
                }
                name, exe, dir_name = app_names.get(app_name, ("", "", ""))
                app_path = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / dir_name
                    / exe
                )

                if app_path.exists():
                    self.log(f"Found application at: {app_path}", "success")
                    # Automatically create desktop entry
                    # Call directly - create_desktop_entry uses signals so it's thread-safe
                    try:
                        self.create_desktop_entry(app_name)
                        self.log("Desktop entry created successfully", "success")
                    except Exception as e:
                        self.log(f"Error creating desktop entry: {e}", "error")
                else:
                    self.log(
                        f"Warning: Application not found at expected path: {app_path}",
                        "warning",
                    )
                    self.log(
                        "Desktop entry will not be created automatically.", "warning"
                    )

                display_name = {
                    "Photo": "Affinity Photo",
                    "Designer": "Affinity Designer",
                    "Publisher": "Affinity Publisher",
                }.get(app_name, app_name)

                self.log(f"\n✓ {display_name} installation completed!", "success")
                self.log("You can now launch it from your application menu.", "info")

                self.show_message(
                    "Installation Complete",
                    f"{display_name} has been successfully installed!\n\n"
                    "You can launch it from your application menu.",
                    "info",
                )
            else:
                # For non-Affinity apps, just complete without desktop entry
                display_name = app_name if app_name else "Application"
                self.log(f"\n✓ {display_name} installation completed!", "success")

                # Run AffinityPluginLoader + WineFix automatically after Affinity (Unified) installs
                if app_name == "Add":
                    install_dir = (
                        Path(self.directory)
                        / "drive_c"
                        / "Program Files"
                        / "Affinity"
                        / "Affinity"
                    )
                    if install_dir.exists():
                        self.log(
                            "\nRunning AffinityPluginLoader + WineFix install...",
                            "info",
                        )
                        self._install_affinity_plugin_loader_thread(standalone=False)
                    else:
                        self.log(
                            "\n⚠ Affinity directory not found — skipping AffinityPluginLoader install.",
                            "warning",
                        )

                self.show_message(
                    "Installation Complete",
                    f"{display_name} has been successfully installed!\n\n"
                    "You may need to create a desktop entry manually if needed.",
                    "info",
                )
        except Exception as e:
            self.log(f"Installation error: {e}", "error")
            self.show_message("Installation Error", f"An error occurred:\n{e}", "error")

    def create_custom_desktop_entry(self, installer_path, app_name):
        """Create desktop entry for custom installed app"""
        reply = QMessageBox.question(
            self,
            "Create Desktop Entry",
            f"Would you like to create a desktop entry for '{app_name}'?\n\n"
            "You'll need to provide the executable path.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Ask for executable path
        exe_path, ok = QInputDialog.getText(
            self,
            "Executable Path",
            f"Enter the full path to the {app_name} executable:\n\n"
            "Example: C:\\Program Files\\MyApp\\MyApp.exe",
        )

        if not ok or not exe_path:
            self.log("Desktop entry creation cancelled.", "warning")
            return

        # Ask for icon path (optional)
        icon_path, ok = QInputDialog.getText(
            self,
            "Icon Path (Optional)",
            "Enter the path to an icon file (optional):\n\n"
            "Leave blank to use default icon.",
        )

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = desktop_dir / f"{app_name.replace(' ', '')}.desktop"

        wine = self.get_wine_path("wine")

        # Normalize all paths to strings to avoid double slashes
        wine_str = str(wine)
        directory_str = str(self.directory).rstrip(
            "/"
        )  # Remove trailing slash if present

        # Normalize path: convert Windows backslashes to forward slashes, remove double slashes
        exe_path_normalized = exe_path.replace("\\", "/").replace("//", "/")
        # If it's a Windows path starting with C:, convert to Linux path
        if exe_path_normalized.startswith("C:/"):
            exe_path_normalized = directory_str + "/drive_c" + exe_path_normalized[2:]

        # Get GPU environment variables if configured
        gpu_env = self.get_gpu_env_vars()
        # Get DXVK environment variables if AMD GPU is detected
        dxvk_env = self.get_dxvk_env_vars()

        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\n")
            f.write(f"Name={app_name}\n")
            f.write(f"Comment={app_name} installed via Affinity Linux Installer\n")
            if icon_path:
                icon_path_str = str(icon_path).rstrip("/")
                f.write(f"Icon={icon_path_str}\n")
            f.write(f"Path={directory_str}\n")
            # Use Linux path format with proper quoting for spaces
            # Include GPU environment variables if configured
            exec_line = f"Exec=env WINEPREFIX={directory_str}"
            if gpu_env:
                exec_line += f" {gpu_env}"
            if dxvk_env:
                exec_line += f" {dxvk_env}"
            exec_line += f' {wine_str} "{exe_path_normalized}"'
            f.write(f"{exec_line}\n")
            f.write("Terminal=false\n")
            f.write("Type=Application\n")
            f.write("Categories=Application;\n")
            f.write("StartupNotify=true\n")

        self.log(f"Desktop entry created: {desktop_file}", "success")

    def update_application(self, app_name):
        """Update Affinity application - simple installer that assumes everything is set up"""
        app_names = {
            "Add": "Affinity (Unified)",
            "Photo": "Affinity Photo",
            "Designer": "Affinity Designer",
            "Publisher": "Affinity Publisher",
        }

        display_name = app_names.get(app_name, app_name)

        self.log(
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log(f"Update {display_name}", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine = self.get_wine_path("wine")
        if not wine.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # Ask for installer file
        self.log(f"Please select the {display_name} installer (.exe)...", "info")

        installer_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {display_name} Installer",
            "",
            "Executable files (*.exe);;All files (*.*)",
        )

        if not installer_path:
            self.log("Update cancelled.", "warning")
            return

        # Start operation and update in thread
        self.start_operation(f"Update {display_name}")
        threading.Thread(
            target=self._run_update_entry,
            args=(display_name, installer_path),
            daemon=True,
        ).start()

    def _run_update_entry(self, display_name, installer_path):
        """Wrapper: run update and always end operation."""
        try:
            self.run_update(display_name, installer_path)
        finally:
            self.end_operation()

    def run_update(self, display_name, installer_path):
        """Run the update process - simple installer without desktop entries or deps"""
        try:
            self.update_progress_text("Preparing update...")
            self.update_progress(0.0)
            self.log(f"Selected installer: {installer_path}", "success")

            # Copy installer to Wine prefix with sanitized filename (remove spaces)
            self.update_progress_text("Copying installer...")
            self.update_progress(0.2)
            original_filename = Path(installer_path).name
            sanitized_filename = self.sanitize_filename(original_filename)
            installer_file = Path(self.directory) / sanitized_filename
            shutil.copy2(installer_path, installer_file)
            self.log(
                f"Installer copied to Wine prefix: {installer_file} (WINEPREFIX={self.directory})",
                "success",
            )

            # Set up environment
            self.update_progress_text("Configuring Wine...")
            self.update_progress(0.3)
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory

            # Use regular Wine for all installations (wine-tkg is only for winetricks)
            wine_cfg = self.get_wine_path("winecfg")
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            env["WINEDEBUG"] = "-all"

            # Run installer with custom Wine
            self.update_progress_text("Running updater...")
            self.update_progress(0.4)
            # Wine will be determined by _run_installer_and_capture based on installer type
            self.log("Launching installer...", "info")
            self.log("Follow the installation wizard in the window that opens.", "info")
            self.log(
                "This will update the application without creating desktop entries.",
                "info",
            )

            # Run updater and wait, capturing logs (with fallback)
            success = self._run_installer_and_capture(
                installer_file, env, label="updater"
            )
            if not success and not self.check_cancelled():
                self.log("Updater process exited with a non-zero status", "warning")

            # Clean up installer
            if installer_file.exists():
                installer_file.unlink()
                self.log("Installer file removed", "success")

            # Remove Wine desktop entries created by the installer
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            wine_desktop_dir = desktop_dir / "wine" / "Programs"

            # Ensure display_name is a string
            if not isinstance(display_name, str):
                display_name = str(display_name) if display_name is not None else ""

            # Map display names to possible Wine desktop entry names
            wine_entry_names = []
            if display_name and (
                "Suite" in display_name or display_name == "Affinity Suite"
            ):
                wine_entry_names = ["Affinity.desktop"]
            elif display_name and "Photo" in display_name:
                wine_entry_names = [
                    "Affinity Photo 2.desktop",
                    "Affinity Photo.desktop",
                ]
            elif display_name and "Designer" in display_name:
                wine_entry_names = [
                    "Affinity Designer 2.desktop",
                    "Affinity Designer.desktop",
                ]
            elif display_name and "Publisher" in display_name:
                wine_entry_names = [
                    "Affinity Publisher 2.desktop",
                    "Affinity Publisher.desktop",
                ]

            removed_count = 0
            for entry_name in wine_entry_names:
                wine_entry = wine_desktop_dir / entry_name
                if wine_entry.exists():
                    try:
                        wine_entry.unlink()
                        removed_count += 1
                        self.log(f"Removed Wine desktop entry: {entry_name}", "info")
                    except Exception as e:
                        self.log(f"Could not remove {entry_name}: {e}", "error")

            # Also check for generic Affinity.desktop if not already checked
            if display_name and "Unified" not in display_name:
                generic_entry = wine_desktop_dir / "Affinity.desktop"
                if generic_entry.exists():
                    try:
                        generic_entry.unlink()
                        self.log("Removed Wine desktop entry: Affinity.desktop", "info")
                    except Exception as e:
                        self.log(f"Could not remove Affinity.desktop: {e}", "error")

            if removed_count > 0:
                self.log(
                    f"Cleaned up {removed_count} Wine desktop entr{'y' if removed_count == 1 else 'ies'}",
                    "success",
                )

            # Reinstall WinMetadata to avoid corruption
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Reinstalling WinMetadata to prevent corruption...", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Kill Wine processes before removing WinMetadata
            self.log("Stopping Wine processes...", "info")
            self.run_command(["wineserver", "-k"], check=False)
            time.sleep(2)

            system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
            winmetadata_dir = system32_dir / "WinMetadata"

            # Remove existing WinMetadata folder
            if winmetadata_dir.exists():
                self.log("Removing existing WinMetadata folder...", "info")
                try:
                    shutil.rmtree(winmetadata_dir)
                    self.log("Old WinMetadata folder removed", "success")
                except Exception as e:
                    self.log(
                        f"Warning: Could not fully remove old folder: {e}", "warning"
                    )

            # Reinstall WinMetadata by downloading and extracting
            self.log("Installing fresh WinMetadata...", "info")
            self.setup_winmetadata()

            # For Affinity v3 (Unified), reinstall settings files
            if display_name and (
                "Unified" in display_name or display_name == "Affinity (Unified)"
            ):
                # Reinstall settings files
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Reinstalling Affinity v3 settings files...", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self._install_affinity_settings_thread()

                # Patch the DLL to fix settings saving (this is the last step)
                self.update_progress_text("Patching DLL for settings fix...")
                self.update_progress(0.95)
                patch_success = self.patch_affinity_dll(display_name)
                if patch_success:
                    self.log("Settings fix patch applied successfully", "success")
                else:
                    self.log(
                        "Settings fix patch was skipped or failed (check log for details)",
                        "warning",
                    )

            self.update_progress(1.0)
            self.update_progress_text("Update complete!")
            self.log(f"\n✓ {display_name} update completed!", "success")
            self.log(
                "The application has been updated. Use your existing desktop entry to launch it.",
                "info",
            )

            # Refresh installation status to update button states
            QTimer.singleShot(100, self.check_installation_status)

            message_text = f"{display_name} has been successfully updated!\n\n"
            message_text += "WinMetadata has been reinstalled to prevent corruption.\n"
            if display_name and (
                "Unified" in display_name or display_name == "Affinity (Unified)"
            ):
                message_text += "Affinity v3 settings have been reinstalled.\n"
                message_text += "Settings fix patch has been applied (settings should now save properly).\n"
            message_text += "Use your existing desktop entry to launch the application."

            self.show_message("Update Complete", message_text, "info")
        except Exception as e:
            self.log(f"Update error: {e}", "error")
            self.show_message("Update Error", f"An error occurred:\n{e}", "error")

    def _run_installation_entry(self, app_name, installer_path):
        """Wrapper: run installation and always end operation."""
        try:
            self.run_installation(app_name, installer_path)
        finally:
            self.end_operation()

    def run_installation(self, app_name, installer_path):
        """Run the installation process"""
        try:
            self.update_progress_text("Preparing installation...")
            self.update_progress(0.0)
            self.log(f"Selected installer: {installer_path}", "success")

            # Check if installer is already in .AffinityLinux/Installer/ (downloaded installer)
            installer_path_obj = Path(installer_path)
            installer_dir = Path(self.directory) / "Installer"

            # If installer is in .AffinityLinux/Installer/, use it directly
            if installer_path_obj.parent == installer_dir:
                self.log(
                    f"Using installer from .AffinityLinux/Installer/: {installer_path_obj.name}",
                    "info",
                )
                installer_file = installer_path_obj
            else:
                # For custom installers, copy to Wine prefix with sanitized filename (remove spaces)
                self.update_progress_text("Copying installer...")
                self.update_progress(0.1)
                original_filename = installer_path_obj.name
                sanitized_filename = self.sanitize_filename(original_filename)
                installer_file = Path(self.directory) / sanitized_filename
                shutil.copy2(installer_path, installer_file)
                self.log(
                    f"Installer copied to Wine prefix: {installer_file} (WINEPREFIX={self.directory})",
                    "success",
                )

            # Set Windows version
            self.update_progress_text("Configuring Wine...")
            self.update_progress(0.2)
            # Check if this is Affinity v3 or v2
            installer_name = installer_file.name.lower()
            is_affinity_v3 = (
                app_name == "Add" or app_name == "Affinity (Unified)"
            ) or (
                "affinity" in installer_name
                and ("x64" in installer_name or "affinity-x64" in installer_name)
            )
            is_affinity_v2 = (
                any(app in installer_name for app in ["photo", "designer", "publisher"])
                and ".exe" in installer_name
            )

            # Use regular Wine for all installations (wine-tkg is only for winetricks)
            wine_cfg = self.get_wine_path("winecfg")
            wine = self.get_wine_path("wine")

            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            # Run installer
            self.update_progress_text("Running installer...")
            self.update_progress(0.3)

            env["WINEDEBUG"] = "-all"
            self.log("Launching installer...", "info")
            self.log("Follow the installation wizard in the window that opens.", "info")
            self.log("Click 'No' if you encounter any errors.", "warning")

            # Run installer and wait, capturing logs (with fallback)
            success = self._run_installer_and_capture(
                installer_file, env, label="installer"
            )
            if not success and not self.check_cancelled():
                self.log("Installer process exited with a non-zero status", "warning")

            # Clean up installer (only if it was copied to Wine prefix, not if it's in .AffinityLinux/Installer/)
            self.update_progress(0.5)
            if installer_file.parent != installer_dir:
                # Only remove if it was copied (not the original in Installer folder)
                if installer_file.exists():
                    installer_file.unlink()
                    self.log("Installer file removed", "success")
            else:
                self.log(
                    f"Installer kept in .AffinityLinux/Installer/: {installer_file.name}",
                    "info",
                )

            # Restore WinMetadata (only needed for Wine 9.14 and 10.10, not 11.0+)
            wine_version = self.get_current_wine_version()
            if wine_version in ["9.14", "10.10"]:
                self.update_progress_text("Restoring Windows Metadata...")
                self.update_progress(0.6)
                self.restore_winmetadata()
            else:
                self.log(
                    "Skipping WinMetadata restore for Wine 11.0+ (not needed)", "info"
                )

            # Configure OpenCL (if enabled)
            if self.is_opencl_enabled():
                self.update_progress_text("Configuring OpenCL...")
                self.update_progress(0.7)
                self.configure_opencl(app_name)
            else:
                self.log("OpenCL support is disabled, skipping configuration", "info")

            # For Affinity v2 apps (Photo, Designer, Publisher), copy wintypes.dll and set override (only for Wine < 11.0)
            if is_affinity_v2:
                wine_version = self.get_current_wine_version()
                if wine_version in ["9.14", "10.10"]:
                    self.update_progress_text("Configuring wintypes.dll for v2 app...")
                    self.update_progress(0.82)
                    self.setup_wintypes_dll(app_name)
                else:
                    self.log(
                        "Skipping wintypes.dll setup for Wine 11.0+ (not needed)",
                        "info",
                    )

            # For Affinity v3 (Unified), copy wintypes.dll and set override, then patch the DLL (only for Wine < 11.0)
            if app_name == "Add" or app_name == "Affinity (Unified)":
                wine_version = self.get_current_wine_version()
                if wine_version in ["9.14", "10.10"]:
                    # Copy wintypes.dll and set override
                    self.update_progress_text("Configuring wintypes.dll for v3 app...")
                    self.update_progress(0.82)
                    self.setup_wintypes_dll(app_name)
                else:
                    self.log(
                        "Skipping wintypes.dll setup for Wine 11.0+ (not needed)",
                        "info",
                    )

                # Patch the DLL to fix settings saving
                self.update_progress_text("Patching DLL for settings fix...")
                self.update_progress(0.85)
                self.patch_affinity_dll(app_name)

            # Create desktop entry
            self.update_progress_text("Creating desktop entry...")
            self.update_progress(0.9)
            self.create_desktop_entry(app_name)

            # Run AffinityPluginLoader + WineFix automatically after Affinity (Unified) installs
            if app_name in ["Add", "Affinity (Unified)"]:
                install_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / "Affinity"
                )
                if install_dir.exists():
                    self.update_progress_text(
                        "Installing AffinityPluginLoader + WineFix..."
                    )
                    self.log(
                        "\nRunning AffinityPluginLoader + WineFix install...", "info"
                    )
                    self._install_affinity_plugin_loader_thread(standalone=False)
                else:
                    self.log(
                        "\n⚠ Affinity directory not found — skipping AffinityPluginLoader install.",
                        "warning",
                    )

            self.update_progress(1.0)
            self.update_progress_text("Installation complete!")
            self.log(f"\n✓ {app_name} installation completed!", "success")
            self.log("You can now launch it from your application menu.", "info")

            self.show_message(
                "Installation Complete",
                f"{app_name} has been successfully installed!\n\n"
                "You can launch it from your application menu.",
                "info",
            )
        except Exception as e:
            self.log(f"Installation error: {e}", "error")
            self.show_message("Installation Error", f"An error occurred:\n{e}", "error")

    def setup_wintypes_dll(self, app_name):
        """Download and copy wintypes.dll next to exe and set up DLL override for Affinity v2 and v3 apps"""
        try:
            # Get app directory and exe path
            app_dir = None
            exe_path = None

            # Handle v2 apps (Photo, Designer, Publisher)
            if app_name in ["Photo", "Designer", "Publisher"]:
                app_names = {
                    "Photo": ("Photo 2", "Photo.exe"),
                    "Designer": ("Designer 2", "Designer.exe"),
                    "Publisher": ("Publisher 2", "Publisher.exe"),
                }
                dir_name, exe = app_names.get(app_name, (None, None))
                if dir_name and exe:
                    app_dir = (
                        Path(self.directory)
                        / "drive_c"
                        / "Program Files"
                        / "Affinity"
                        / dir_name
                    )
                    exe_path = app_dir / exe

            # Handle v3 (Unified) app
            elif app_name == "Add" or app_name == "Affinity (Unified)":
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / "Affinity"
                )
                exe_path = app_dir / "Affinity.exe"

            if not app_dir or not exe_path or not exe_path.exists():
                self.log(
                    f"Exe not found for {app_name}, skipping wintypes.dll setup",
                    "warning",
                )
                return

            # Download wintypes.dll to temp location first
            temp_dir = Path(self.directory) / ".temp_wintypes"
            temp_dir.mkdir(exist_ok=True)
            wintypes_temp = temp_dir / "wintypes.dll"

            if not self._download_wintypes_dll(wintypes_temp):
                self.log(f"Failed to download wintypes.dll for {app_name}", "warning")
                return

            # Copy wintypes.dll next to exe
            wintypes_dest = app_dir / "wintypes.dll"
            shutil.copy2(wintypes_temp, wintypes_dest)
            self.log(f"Copied wintypes.dll to {wintypes_dest}", "success")

            # Clean up temp file
            try:
                wintypes_temp.unlink()
            except Exception:
                pass

            # Set up DLL override for wintypes.dll as Native (Windows)
            self.setup_wintypes_dll_override()
        except Exception as e:
            self.log(f"Error setting up wintypes.dll: {e}", "warning")

    def setup_wintypes_dll_override(self):
        """Set up DLL override for wintypes.dll as Native (Windows)"""
        try:
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory

            # Check if override already exists
            wine = self.get_wine_path("wine")
            success_check, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    "wintypes",
                ],
                check=False,
                env=env,
                capture=True,
            )

            if success_check and "native" in stdout:
                self.log("wintypes.dll override already configured", "info")
            else:
                # Create registry file for wintypes override
                reg_file = Path(self.directory) / "wintypes_override.reg"
                with open(reg_file, "w") as f:
                    f.write("REGEDIT4\n")
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]\n")
                    f.write('"wintypes"="native"\n')

                regedit = self.get_wine_path("regedit")
                reg_success, _, stderr = self.run_command(
                    [str(regedit), str(reg_file)], check=False, env=env, capture=True
                )
                reg_file.unlink()

                if reg_success:
                    self.log(
                        "wintypes.dll override configured as Native (Windows)",
                        "success",
                    )
                else:
                    self.log(
                        f"Warning: Could not configure wintypes.dll override: {stderr}",
                        "warning",
                    )
        except Exception as e:
            self.log(f"Error setting up wintypes.dll override: {e}", "warning")

    def copy_wintypes_dll_for_all_apps(self):
        """Download and copy wintypes.dll for all installed Affinity apps (v2 and v3)"""
        try:
            affinity_dir = (
                Path(self.directory) / "drive_c" / "Program Files" / "Affinity"
            )
            if not affinity_dir.exists():
                self.log("Affinity installation directory not found", "warning")
                return

            # Download wintypes.dll to temp location first
            temp_dir = Path(self.directory) / ".temp_wintypes"
            temp_dir.mkdir(exist_ok=True)
            wintypes_temp = temp_dir / "wintypes.dll"

            if not self._download_wintypes_dll(wintypes_temp):
                self.log("Failed to download wintypes.dll", "warning")
                return

            copied_count = 0

            # Check for v2 apps (Photo 2, Designer 2, Publisher 2)
            v2_apps = [
                ("Photo 2", "Photo.exe"),
                ("Designer 2", "Designer.exe"),
                ("Publisher 2", "Publisher.exe"),
            ]

            for dir_name, exe in v2_apps:
                app_dir = affinity_dir / dir_name
                exe_path = app_dir / exe

                if exe_path.exists():
                    wintypes_dest = app_dir / "wintypes.dll"
                    try:
                        shutil.copy2(wintypes_temp, wintypes_dest)
                        self.log(f"Copied wintypes.dll to {wintypes_dest}", "info")
                        copied_count += 1
                    except Exception as e:
                        self.log(
                            f"Warning: Could not copy wintypes.dll to {dir_name}: {e}",
                            "warning",
                        )

            # Check for v3 (Unified) app
            v3_app_dir = affinity_dir / "Affinity"
            v3_exe_path = v3_app_dir / "Affinity.exe"

            if v3_exe_path.exists():
                wintypes_dest = v3_app_dir / "wintypes.dll"
                try:
                    shutil.copy2(wintypes_temp, wintypes_dest)
                    self.log(f"Copied wintypes.dll to {wintypes_dest}", "info")
                    copied_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not copy wintypes.dll to Affinity v3: {e}",
                        "warning",
                    )

            # Clean up temp file
            try:
                wintypes_temp.unlink()
            except Exception:
                pass

            if copied_count > 0:
                self.log(f"Copied wintypes.dll for {copied_count} app(s)", "success")
            else:
                self.log("No Affinity apps found to copy wintypes.dll", "info")
        except Exception as e:
            self.log(f"Error copying wintypes.dll for all apps: {e}", "warning")

    def restore_winmetadata(self):
        """Restore WinMetadata after installation"""
        self.log("Restoring Windows metadata files...", "info")

        # Kill Wine processes
        self.run_command(["wineserver", "-k"], check=False)
        time.sleep(2)

        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        system32_dir.mkdir(parents=True, exist_ok=True)

        try:
            winmetadata_dest = system32_dir / "WinMetadata"

            # Remove existing WinMetadata if it exists
            if winmetadata_dest.exists():
                shutil.rmtree(winmetadata_dest)
                self.log("Removed existing WinMetadata folder", "info")

            # Download and extract WinMetadata
            if not self._download_and_extract_winmetadata(system32_dir):
                self.log("Failed to restore WinMetadata", "warning")
                return

            # Verify WinMetadata was extracted
            if not winmetadata_dest.exists():
                self.log("WinMetadata restoration failed - folder not found", "warning")
                return

            self.log("WinMetadata restored", "success")
        except Exception as e:
            self.log(f"Failed to restore WinMetadata: {e}", "warning")

    def is_opencl_enabled(self):
        """Check if OpenCL is enabled"""
        # First check instance variable (set during one-click setup)
        if hasattr(self, "enable_opencl") and self.enable_opencl:
            return True

        # Check saved preference
        opencl_config_file = Path(self.directory) / ".opencl_enabled"
        if opencl_config_file.exists():
            try:
                with open(opencl_config_file, "r") as f:
                    content = f.read().strip()
                    return content == "1"
            except Exception:
                pass

        return False

    def get_renderer_setting(self):
        """Get the current renderer setting from registry (vulkan, opengl, or gdi)"""
        try:
            wine = self.get_wine_path("wine")
            if not wine.exists():
                return "vulkan"  # Default to vulkan if Wine not set up

            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory

            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                    "/v",
                    "renderer",
                ],
                check=False,
                env=env,
                capture=True,
            )

            if success and stdout:
                stdout_lower = stdout.lower()
                if "opengl" in stdout_lower:
                    return "opengl"
                elif "gdi" in stdout_lower:
                    return "gdi"
                elif "vulkan" in stdout_lower:
                    return "vulkan"

            # Default to vulkan if not found
            return "vulkan"
        except Exception:
            return "vulkan"  # Default to vulkan on error

    def configure_opencl(self, app_name):
        """Configure d3d12 DLLs for application (needed even when using DXVK)"""
        app_dirs = {
            "Photo": "Photo 2",
            "Designer": "Designer 2",
            "Publisher": "Publisher 2",
            "Add": "Affinity",
        }

        app_dir_name = app_dirs.get(app_name, "Affinity")
        app_dir = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / app_dir_name
        )

        if not app_dir.exists():
            self.log(f"Application directory not found: {app_dir}", "warning")
            return

        wine_lib_dir = (
            self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
        )
        vkd3d_temp = Path(self.directory) / "vkd3d_dlls"

        # Ensure DLLs are installed in Wine library first
        if not wine_lib_dir.exists() or not (wine_lib_dir / "d3d12.dll").exists():
            self.log("d3d12 DLLs not found in Wine library, installing...", "info")
            self.install_d3d12_dlls()

        dlls_copied = 0
        for dll in ["d3d12.dll", "d3d12core.dll"]:
            for source in [vkd3d_temp / dll, wine_lib_dir / dll]:
                if source.exists():
                    shutil.copy2(source, app_dir / dll)
                    self.log(f"Copied {dll} to {app_dir_name}", "success")
                    dlls_copied += 1
                    break

        # Ensure DLL overrides are set up
        self.setup_d3d12_overrides()

        if dlls_copied > 0:
            self.log(f"d3d12 DLLs configured for {app_dir_name}", "success")

    def enable_opencl_support(self):
        """Enable OpenCL support for Affinity applications"""
        # Check if Wine is set up
        wine = self.get_wine_path("wine")
        if not wine.exists():
            QMessageBox.warning(
                self,
                "Wine Not Installed",
                "Wine must be installed before enabling OpenCL support.\n\n"
                "Please run 'One-Click Setup' or 'Setup Wine Environment' first.",
            )
            return

        # Check if OpenCL is already enabled
        if self.is_opencl_enabled():
            reply = QMessageBox.question(
                self,
                "OpenCL Already Enabled",
                "OpenCL support is already enabled.\n\n"
                "Would you like to reconfigure OpenCL support?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Enable OpenCL Support",
            "OpenCL (Open Computing Language) enables hardware acceleration for certain features in Affinity applications.\n\n"
            "This will:\n"
            "• Download and configure vkd3d-proton (or d3d12 DLLs for AMD GPUs)\n"
            "• Install AMD OpenCL dependencies if AMD GPU is detected\n"
            "• Configure OpenCL for all installed Affinity applications\n\n"
            "Would you like to enable OpenCL support?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Run in a thread to avoid blocking UI
        def enable_opencl_thread():
            try:
                self.update_progress(0.0)
                self.update_progress_text("Enabling OpenCL support...")
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Enabling OpenCL Support", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )

                # Set OpenCL preference
                self.enable_opencl = True
                self.update_progress(0.1)

                # Save OpenCL preference
                opencl_config_file = Path(self.directory) / ".opencl_enabled"
                try:
                    with open(opencl_config_file, "w") as f:
                        f.write("1")
                    self.log("OpenCL preference saved", "success")
                    # Verify it was saved correctly
                    if opencl_config_file.exists():
                        with open(opencl_config_file, "r") as f:
                            content = f.read().strip()
                            if content == "1":
                                self.log("OpenCL preference verified", "success")
                            else:
                                self.log(
                                    f"Warning: OpenCL preference file contains '{content}' instead of '1'",
                                    "warning",
                                )
                    else:
                        self.log(
                            "Error: OpenCL preference file was not created", "error"
                        )
                except Exception as e:
                    self.log(f"Error: Failed to save OpenCL preference: {e}", "error")
                    import traceback

                    self.log(f"Traceback: {traceback.format_exc()}", "error")

                self.update_progress(0.2)

                # Check GPU and set up accordingly
                gpu_id = self.get_selected_gpu()
                if self.has_nvidia_gpu() and (
                    gpu_id.startswith("nvidia_") or gpu_id.startswith("auto")
                ):
                    # Ask NVIDIA users to choose between DXVK and vkd3d
                    preference = self.ask_nvidia_dxvk_vkd3d_choice()
                    self.update_progress(0.4)

                    if preference == "dxvk":
                        self.update_progress_text(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs..."
                        )
                        self.log(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs and setting up DLL overrides",
                            "info",
                        )
                        self.install_d3d12_dlls()
                    else:
                        self.update_progress_text(
                            "Setting up vkd3d-proton for OpenCL..."
                        )
                        self.log("Setting up vkd3d-proton for OpenCL...", "info")
                        self.setup_vkd3d()

                elif self.has_amd_gpu() and (
                    gpu_id.startswith("amd_") or gpu_id.startswith("auto")
                ):
                    self.update_progress_text(
                        "AMD GPU detected - installing OpenCL dependencies..."
                    )
                    self.log(
                        "AMD GPU detected - installing additional OpenCL dependencies...",
                        "info",
                    )

                    amd_deps = []
                    install_cmd = None

                    # Fedora
                    if self.distro == "fedora":
                        if self.distro_version == "43":
                            amd_deps = [
                                "mesa-opencl-icd",
                                "ocl-icd",
                                "rocm-opencl",
                                "rocm-hip",
                                "wine-opencl",
                            ]
                            self.log(
                                "Fedora 43 detected - installing Fedora 43 specific AMD OpenCL dependencies...",
                                "info",
                            )
                        else:
                            amd_deps = [
                                "rocm-opencl",
                                "apr",
                                "apr-util",
                                "zlib",
                                "libxcrypt-compat",
                                "libcurl",
                                "libcurl-devel",
                                "mesa-libGLU",
                            ]
                        install_cmd = ["sudo", "dnf", "install", "-y"] + amd_deps

                    # Arch-based distributions
                    elif self.distro in ["arch", "cachyos", "endeavouros", "xerolinux"]:
                        amd_deps = [
                            "opencl-mesa",
                            "ocl-icd",
                            "rocm-opencl-runtime",
                            "rocm-hip",
                            "wine-opencl",
                        ]
                        self.log(
                            f"{self.format_distro_name()} detected - installing Arch-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = [
                            "sudo",
                            "pacman",
                            "-S",
                            "--needed",
                            "--noconfirm",
                        ] + amd_deps

                    # PikaOS (Ubuntu/Debian-based)
                    elif self.distro == "pikaos":
                        amd_deps = [
                            "mesa-opencl-icd",
                            "ocl-icd-libopencl1",
                            "rocm-opencl-runtime",
                            "rocm-hip-runtime",
                        ]
                        self.log(
                            "PikaOS detected - installing Debian/Ubuntu-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = ["sudo", "apt", "install", "-y"] + amd_deps

                    # Install dependencies if we have a command
                    if install_cmd and amd_deps:
                        self.log(f"Installing: {', '.join(amd_deps)}", "info")
                        success, stdout, stderr = self.run_command(install_cmd)

                        if success:
                            self.log(
                                "AMD OpenCL dependencies installed successfully",
                                "success",
                            )
                        else:
                            self.log(
                                f"Warning: Failed to install some AMD OpenCL dependencies: {stderr}",
                                "warning",
                            )
                            self.log(
                                "OpenCL may still work, but some features might be limited",
                                "warning",
                            )

                    self.update_progress(0.5)
                    self.update_progress_text("Installing d3d12 DLLs for AMD GPU...")
                    self.install_d3d12_dlls()

                else:
                    self.update_progress(0.4)
                    self.update_progress_text("Setting up vkd3d-proton for OpenCL...")
                    self.log("Setting up vkd3d-proton for OpenCL...", "info")
                    self.setup_vkd3d()

                self.update_progress(0.8)

                # Configure OpenCL for all installed Affinity applications
                self.update_progress_text(
                    "Configuring OpenCL for Affinity applications..."
                )
                apps_to_configure = []

                # Check which apps are installed
                app_dirs = {
                    "Photo": "Photo 2",
                    "Designer": "Designer 2",
                    "Publisher": "Publisher 2",
                    "Add": "Affinity",
                }

                for app_name, app_dir_name in app_dirs.items():
                    app_dir = (
                        Path(self.directory)
                        / "drive_c"
                        / "Program Files"
                        / "Affinity"
                        / app_dir_name
                    )
                    if app_dir.exists():
                        apps_to_configure.append(app_name)

                if apps_to_configure:
                    self.log(
                        f"Configuring OpenCL for: {', '.join(apps_to_configure)}",
                        "info",
                    )
                    for app_name in apps_to_configure:
                        self.configure_opencl(app_name)
                else:
                    self.log("No Affinity applications found to configure", "info")

                # Apply OpenCL event callback and libraster patches
                self.update_progress_text("Applying OpenCL acceleration patches...")
                self.ensure_opencl_patch_files(silent=True)
                self.install_opencl_dll_patch()
                self.run_libraster_patcher()

                self.update_progress(1.0)
                self.update_progress_text("OpenCL support enabled!")

                # Verify OpenCL is enabled
                if self.is_opencl_enabled():
                    self.log(
                        "\n✓ OpenCL support has been enabled successfully!", "success"
                    )
                    self.log(
                        "OpenCL is now configured for all installed Affinity applications.",
                        "info",
                    )
                    # Show success message on main thread
                    QTimer.singleShot(
                        0,
                        lambda: QMessageBox.information(
                            self,
                            "OpenCL Enabled",
                            "OpenCL support has been successfully enabled!\n\n"
                            "OpenCL is now configured for all installed Affinity applications.\n"
                            "You may need to restart Affinity applications for the changes to take effect.",
                        ),
                    )
                else:
                    self.log(
                        "\n⚠ Warning: OpenCL preference may not have been saved correctly",
                        "warning",
                    )
                    self.log(
                        "Please check the .opencl_enabled file in your Affinity directory",
                        "warning",
                    )
                    QTimer.singleShot(
                        0,
                        lambda: QMessageBox.warning(
                            self,
                            "OpenCL Warning",
                            "OpenCL support was configured, but the preference may not have been saved correctly.\n\n"
                            "Please check the log for details.",
                        ),
                    )

                # Refresh installation status
                QTimer.singleShot(100, self.check_installation_status)

            except Exception as e:
                import traceback

                error_msg = str(e)
                error_trace = traceback.format_exc()
                self.log(f"Error enabling OpenCL support: {error_msg}", "error")
                self.log(f"Traceback: {error_trace}", "error")
                self.update_progress_text("Error enabling OpenCL support")
                # Use QTimer to show message box on main thread
                QTimer.singleShot(
                    0,
                    lambda: QMessageBox.critical(
                        self,
                        "Error",
                        f"An error occurred while enabling OpenCL support:\n\n{error_msg}\n\nCheck the log for details.",
                    ),
                )

        # Start the thread
        thread = threading.Thread(target=enable_opencl_thread, daemon=True)
        thread.start()

    def _parse_version(self, version_str):
        """Parse version string and return tuple of (major, minor, patch) for comparison"""
        try:
            # Remove any non-numeric suffixes (e.g., "8.0.100-preview" -> "8.0.100")
            version_str = version_str.strip().split("-")[0].split("+")[0]
            parts = version_str.split(".")
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return (major, minor, patch)
        except (ValueError, IndexError):
            return (0, 0, 0)

    def _is_version_sufficient(self, version_str, min_major=8):
        """Check if version is 8.0 or newer"""
        major, minor, patch = self._parse_version(version_str)
        return major >= min_major

    def check_dotnet_sdk_10(self):
        """Check if .NET SDK version 10.0 or newer is installed"""
        # First, try to run dotnet --version
        success, stdout, _ = self.run_command(
            ["dotnet", "--version"], check=False, capture=True
        )
        if success and stdout:
            version = stdout.strip()
            major, minor, patch = self._parse_version(version)
            if major >= 10:
                self.log(f".NET SDK 10.0+ found (version {version})", "success")
                return True
            else:
                self.log(
                    f".NET SDK found but version {version} is too old (need 10.0+)",
                    "warning",
                )
                return False

        # If dotnet command not found, check if it's installed via package manager
        if self.distro in ["fedora", "nobara"]:
            success, stdout, _ = self.run_command(
                ["dnf", "list", "installed", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and "installed" in line.lower():
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 10:
                                self.log(
                                    f".NET SDK 10.0+ package found via dnf: {line.split()[0]}",
                                    "success",
                                )
                                return True

        elif self.distro in ["arch", "cachyos", "endeavouros", "xerolinux"]:
            success, stdout, _ = self.run_command(
                ["pacman", "-Q"], check=False, capture=True
            )
            if success and stdout:
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower():
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 10:
                                self.log(
                                    f".NET SDK 10.0+ package found via pacman: {line.split()[0]}",
                                    "success",
                                )
                                return True

        elif self.distro in ["pikaos", "pop", "debian"]:
            success, stdout, _ = self.run_command(
                ["dpkg", "-l", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and line.startswith("ii"):
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 10:
                                self.log(
                                    f".NET SDK 10.0+ package found via dpkg: {line.split()[1]}",
                                    "success",
                                )
                                return True

        return False

    def check_dotnet_sdk(self):
        """Check if .NET SDK version 8.0 or newer is installed"""
        # First, try to run dotnet --version
        success, stdout, _ = self.run_command(
            ["dotnet", "--version"], check=False, capture=True
        )
        if success and stdout:
            version = stdout.strip()
            if self._is_version_sufficient(version):
                self.log(
                    f".NET SDK found (version {version}) - using installed version",
                    "success",
                )
                return True
            else:
                self.log(
                    f".NET SDK found but version {version} is too old (need 8.0+)",
                    "warning",
                )

        common_paths = [
            "/usr/bin/dotnet",
            "/usr/local/bin/dotnet",
            "/opt/dotnet/dotnet",
            Path.home() / ".dotnet" / "dotnet",
            Path.home() / "bin" / "dotnet" / "dotnet",
            Path.home() / "bin" / "dotnet",
        ]
        # Also check DOTNET_ROOT environment variable if set
        dotnet_root = os.environ.get("DOTNET_ROOT")
        if dotnet_root:
            common_paths.insert(0, Path(dotnet_root) / "dotnet")
            common_paths.insert(1, Path(dotnet_root))

        for path in common_paths:
            path_obj = Path(path)
            if path_obj.exists() and path_obj.is_file():
                # Try running it
                success, stdout, _ = self.run_command(
                    [str(path), "--version"], check=False, capture=True
                )
                if success and stdout:
                    version = stdout.strip()
                    if self._is_version_sufficient(version):
                        self.log(
                            f".NET SDK found at {path}: {version} - using installed version",
                            "success",
                        )
                        return True

        # If dotnet command not found, check if it's installed via package manager
        # This is useful when dotnet is installed but not in PATH
        if self.distro in ["fedora", "nobara"]:
            # Check for any dotnet-sdk package (not just 8.0)
            success, stdout, _ = self.run_command(
                ["dnf", "list", "installed", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                # Look for any dotnet-sdk package
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and "installed" in line.lower():
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                self.log(
                                    f".NET SDK package found via dnf: {line.split()[0]}",
                                    "success",
                                )
                                # Try to find dotnet in common locations
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                    "/opt/dotnet/dotnet",
                                    Path.home() / ".dotnet" / "dotnet",
                                ]
                                for path in common_paths:
                                    if Path(path).exists():
                                        # Try running it
                                        success, stdout, _ = self.run_command(
                                            [str(path), "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                # Package is installed but dotnet command not accessible
                                self.log(
                                    ".NET SDK package is installed but 'dotnet' command not found in PATH",
                                    "warning",
                                )
                                self.log(
                                    "You may need to add /usr/bin to your PATH or restart your terminal",
                                    "info",
                                )
                                return True  # Return True anyway since package is installed

        elif self.distro in ["arch", "cachyos", "endeavouros", "xerolinux"]:
            # Check for any dotnet-sdk package via pacman
            # Query all installed packages and filter for dotnet-sdk
            success, stdout, _ = self.run_command(
                ["pacman", "-Q"], check=False, capture=True
            )
            if success and stdout:
                # Check all installed packages for dotnet-sdk
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower():
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                package_name = line.split()[0]
                                self.log(
                                    f".NET SDK package found via pacman: {package_name}",
                                    "success",
                                )
                                # Try common paths
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                ]
                                for path in common_paths:
                                    if Path(path).exists():
                                        success, stdout, _ = self.run_command(
                                            [path, "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                return True  # Package is installed

        elif self.distro in ["pikaos", "pop", "debian"]:
            # Check for any dotnet-sdk package via dpkg
            success, stdout, _ = self.run_command(
                ["dpkg", "-l", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                # Look for any dotnet-sdk package
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and line.startswith("ii"):
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                self.log(
                                    f".NET SDK package found via dpkg: {line.split()[1]}",
                                    "success",
                                )
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                ]
                                for path in common_paths:
                                    if Path(path).exists():
                                        success, stdout, _ = self.run_command(
                                            [path, "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                return True  # Package is installed

        elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
            # Check for any dotnet-sdk package via zypper
            success, stdout, _ = self.run_command(
                ["zypper", "search", "-i", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                # Look for any installed dotnet-sdk package
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and "|" in line:
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                # Extract package name (first field before |)
                                package_name = line.split("|")[0].strip()
                                self.log(
                                    f".NET SDK package found via zypper: {package_name}",
                                    "success",
                                )
                                # Try common paths
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                    "/opt/dotnet/dotnet",
                                    Path.home() / ".dotnet" / "dotnet",
                                    Path.home() / "bin" / "dotnet" / "dotnet",
                                    Path.home() / "bin" / "dotnet",
                                ]
                                # Also check DOTNET_ROOT if set
                                dotnet_root = os.environ.get("DOTNET_ROOT")
                                if dotnet_root:
                                    common_paths.insert(0, Path(dotnet_root) / "dotnet")
                                    common_paths.insert(1, Path(dotnet_root))
                                for path in common_paths:
                                    path_obj = Path(path)
                                    if path_obj.exists() and path_obj.is_file():
                                        success, stdout, _ = self.run_command(
                                            [str(path), "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                # Package is installed but dotnet command not accessible
                                self.log(
                                    ".NET SDK package is installed but 'dotnet' command not found in PATH",
                                    "warning",
                                )
                                self.log(
                                    "You may need to add the dotnet directory to your PATH or restart your terminal",
                                    "info",
                                )
                                return True  # Return True anyway since package is installed

        return False

    def ensure_patcher_files(self, silent=False):
        """Ensure AffinityPatcher and ReturnColors files are available in .AffinityLinux/Patch/"""
        try:
            # Destination: .AffinityLinux/Patch/AffinityPatcherSettings/
            dest_patch_dir = Path(self.directory) / "Patch" / "AffinityPatcherSettings"
            dest_patch_dir.mkdir(parents=True, exist_ok=True)

            # Files to copy/download
            files_to_get = {
                "AffinityPatcher.cs": "https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/main/Patch/AffinityPatcherSettings/AffinityPatcher.cs",
                "AffinityPatcher.csproj": "https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/main/Patch/AffinityPatcherSettings/AffinityPatcher.csproj",
            }

            # First, try to copy from local repository if available
            script_dir = Path(__file__).parent
            source_patch_dir = script_dir.parent / "Patch" / "AffinityPatcherSettings"

            files_copied = False
            files_downloaded = False
            all_exist = True

            for filename, github_url in files_to_get.items():
                dest_file = dest_patch_dir / filename

                # Check if file already exists and is valid
                if dest_file.exists():
                    # File already exists, skip
                    continue

                # Try to copy from local repository first
                source_file = source_patch_dir / filename
                if source_file.exists():
                    try:
                        shutil.copy2(source_file, dest_file)
                        files_copied = True
                        if not silent:
                            self.log(
                                f"Copied {filename} to .AffinityLinux/Patch/AffinityPatcherSettings/",
                                "info",
                            )
                        continue
                    except Exception as e:
                        if not silent:
                            self.log(
                                f"Failed to copy {filename} from local: {e}", "warning"
                            )

                # If local copy failed or doesn't exist, download from GitHub
                if not dest_file.exists():
                    if not silent:
                        self.log(f"Downloading {filename} from GitHub...", "info")
                    try:
                        if self.download_file(github_url, str(dest_file), filename):
                            files_downloaded = True
                            if not silent:
                                self.log(
                                    f"Downloaded {filename} to .AffinityLinux/Patch/AffinityPatcherSettings/",
                                    "success",
                                )
                        else:
                            all_exist = False
                            if not silent:
                                self.log(f"Failed to download {filename}", "error")
                    except Exception as e:
                        all_exist = False
                        if not silent:
                            self.log(f"Error downloading {filename}: {e}", "error")

            # Final check - verify all files exist
            for filename in files_to_get.keys():
                dest_file = dest_patch_dir / filename
                if not dest_file.exists():
                    all_exist = False

            # Download ReturnColors from GitHub (still in Patch/ directory, not in AffinityPatcherSettings/)
            returncolors_dest = (
                Path(self.directory) / "Patch" / "return-affinity-colors"
            )
            returncolors_repo = (
                "https://github.com/ShawnTheBeachy/return-affinity-colors.git"
            )

            # Check if ReturnColors project folder exists (it's inside return-affinity-colors/ReturnColors/)
            returncolors_project_exists = (
                returncolors_dest.exists()
                and (returncolors_dest / "ReturnColors").exists()
                and (
                    returncolors_dest / "ReturnColors" / "ReturnColors.csproj"
                ).exists()
            )

            if not returncolors_project_exists:
                if not silent:
                    self.log("Downloading ReturnColors from GitHub...", "info")

                # Try git clone first (preferred method)
                if self.check_command("git"):
                    try:
                        # Remove existing directory if it exists but is incomplete
                        if returncolors_dest.exists():
                            shutil.rmtree(returncolors_dest)

                        # Clone the repository
                        success, stdout, stderr = self.run_command(
                            [
                                "git",
                                "clone",
                                "--depth",
                                "1",
                                returncolors_repo,
                                str(returncolors_dest),
                            ],
                            check=False,
                            capture=True,
                        )

                        if success:
                            if not silent:
                                self.log(
                                    "ReturnColors downloaded from GitHub via git",
                                    "success",
                                )
                        else:
                            if not silent:
                                self.log(
                                    f"Git clone failed: {stderr[:200] if stderr else 'Unknown error'}",
                                    "warning",
                                )
                            # Fall through to zip download
                            if returncolors_dest.exists():
                                shutil.rmtree(returncolors_dest)
                    except Exception as e:
                        if not silent:
                            self.log(f"Error cloning ReturnColors: {e}", "warning")
                        if returncolors_dest.exists():
                            try:
                                shutil.rmtree(returncolors_dest)
                            except:
                                pass

                # Fallback: Download as zip and extract
                if not returncolors_project_exists:
                    try:
                        # Download zip from GitHub
                        zip_url = "https://github.com/ShawnTheBeachy/return-affinity-colors/archive/refs/heads/main.zip"
                        temp_zip = tempfile.NamedTemporaryFile(
                            delete=False, suffix=".zip"
                        )
                        temp_zip_path = Path(temp_zip.name)
                        temp_zip.close()

                        if not silent:
                            self.log(
                                "Downloading ReturnColors as ZIP from GitHub...", "info"
                            )

                        if self.download_file(
                            zip_url, str(temp_zip_path), "ReturnColors ZIP"
                        ):
                            # Extract zip
                            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                                # Extract to a temp directory first
                                temp_extract = dest_patch_dir / ".temp_returncolors"
                                if temp_extract.exists():
                                    shutil.rmtree(temp_extract)
                                temp_extract.mkdir(exist_ok=True)
                                zip_ref.extractall(temp_extract)

                                # Move the extracted folder to the correct location
                                extracted_folder = (
                                    temp_extract / "return-affinity-colors-main"
                                )
                                if extracted_folder.exists():
                                    if returncolors_dest.exists():
                                        shutil.rmtree(returncolors_dest)
                                    extracted_folder.rename(returncolors_dest)

                                # Clean up temp directory
                                if temp_extract.exists():
                                    try:
                                        shutil.rmtree(temp_extract)
                                    except:
                                        pass

                            # Clean up zip file
                            temp_zip_path.unlink()

                            # Verify the structure is correct
                            if (
                                returncolors_dest.exists()
                                and (returncolors_dest / "ReturnColors").exists()
                                and (
                                    returncolors_dest
                                    / "ReturnColors"
                                    / "ReturnColors.csproj"
                                ).exists()
                            ):
                                if not silent:
                                    self.log(
                                        "ReturnColors downloaded and extracted from GitHub",
                                        "success",
                                    )
                            else:
                                if not silent:
                                    self.log(
                                        "ReturnColors extraction failed - folder structure not found",
                                        "warning",
                                    )
                                # Try to find the correct structure
                                if returncolors_dest.exists():
                                    # Check if ReturnColors folder is at the root
                                    if (
                                        returncolors_dest / "ReturnColors.csproj"
                                    ).exists():
                                        # The zip might have extracted differently, move files
                                        pass  # Structure is already correct
                        else:
                            if not silent:
                                self.log(
                                    "Failed to download ReturnColors ZIP from GitHub",
                                    "warning",
                                )
                    except Exception as e:
                        if not silent:
                            self.log(f"Error downloading ReturnColors: {e}", "warning")
            elif not silent:
                self.log("ReturnColors already exists in .AffinityLinux/Patch/", "info")

            if files_copied and not silent:
                self.log("Patcher files are ready in .AffinityLinux/Patch/", "success")
            elif files_downloaded and not silent:
                self.log(
                    "Patcher files downloaded and ready in .AffinityLinux/Patch/",
                    "success",
                )
            elif not all_exist and not silent:
                self.log("Some patcher files are missing", "warning")

            return all_exist
        except Exception as e:
            if not silent:
                self.log(f"Error ensuring patcher files: {e}", "error")
            return False

    def build_affinity_patcher(self):
        """Build the AffinityPatcher .NET project"""
        # Use Patch/AffinityPatcherSettings directory from .AffinityLinux (ensured to be available)
        patch_dir = Path(self.directory) / "Patch" / "AffinityPatcherSettings"

        if not patch_dir.exists():
            self.log(
                f"AffinityPatcherSettings directory not found: {patch_dir}", "error"
            )
            return None

        csproj_file = patch_dir / "AffinityPatcher.csproj"
        if not csproj_file.exists():
            self.log(f"AffinityPatcher.csproj not found: {csproj_file}", "error")
            return None

        self.log(f"Building AffinityPatcher from: {patch_dir}", "info")

        # Build the project - use absolute path and prevent building project references
        # Output directory is within the AffinityPatcherSettings folder
        output_dir = patch_dir / "bin" / "Release"
        # Use --no-incremental for clean build and -p:BuildProjectReferences=false to prevent building other projects
        # Also use absolute path to ensure we're building the correct project
        # The issue is that MSBuild might be picking up files from return-affinity-colors subdirectory
        # So we explicitly build only the project file and disable project references
        csproj_absolute = csproj_file.resolve()
        success, stdout, stderr = self.run_command(
            [
                "dotnet",
                "build",
                str(csproj_absolute),
                "-c",
                "Release",
                "-o",
                str(output_dir.resolve()),
                "--no-incremental",
                "-p:BuildProjectReferences=false",
                "/p:DisableImplicitNuGetFallbackFolder=true",
            ],
            check=False,
            capture=True,
        )

        if not success:
            self.log(f"Failed to build AffinityPatcher: {stderr}", "error")
            if stdout:
                self.log(f"Build output: {stdout}", "warning")
            return None

        # Find the built executable - .NET can create different output formats
        # Try common output names
        possible_names = [
            "AffinityPatcher",  # Native executable (Linux)
            "AffinityPatcher.dll",  # DLL (runnable with dotnet)
            "AffinityPatcher.exe",  # Windows executable (unlikely on Linux)
        ]

        patcher_exe = None
        for name in possible_names:
            candidate = output_dir / name
            if candidate.exists():
                patcher_exe = candidate
                break

        if patcher_exe and patcher_exe.exists():
            self.log(f"AffinityPatcher built successfully: {patcher_exe}", "success")
            return patcher_exe
        else:
            # List what's actually in the output directory for debugging
            if output_dir.exists():
                files = list(output_dir.glob("*"))
                self.log(
                    f"Files in output directory: {[f.name for f in files]}", "warning"
                )
            self.log(
                f"Built patcher not found at expected location: {output_dir}", "error"
            )
            return None

    def run_affinity_patcher(self, dll_path):
        """Run the AffinityPatcher on the specified DLL"""
        if not Path(dll_path).exists():
            self.log(f"DLL not found: {dll_path}", "error")
            return False

        # Build the patcher if needed
        patcher_exe = self.build_affinity_patcher()
        if not patcher_exe:
            self.log("Failed to build AffinityPatcher", "error")
            return False

        self.log(f"Running AffinityPatcher on: {dll_path}", "info")

        # Run the patcher - use dotnet for DLLs, direct execution for native executables
        if patcher_exe.suffix == ".dll":
            cmd = ["dotnet", str(patcher_exe), dll_path]
        else:
            cmd = [str(patcher_exe), dll_path]

        success, stdout, stderr = self.run_command(cmd, check=False, capture=True)

        if success:
            self.log("AffinityPatcher completed successfully", "success")
            if stdout:
                # Log the patcher output
                for line in stdout.strip().split("\n"):
                    if line.strip():
                        if "SUCCESS" in line or "success" in line.lower():
                            self.log(line, "success")
                        elif "ERROR" in line or "error" in line.lower():
                            self.log(line, "error")
                        else:
                            self.log(line, "info")
            return True
        else:
            self.log(f"AffinityPatcher failed: {stderr}", "error")
            if stdout:
                self.log(f"Output: {stdout}", "warning")
            return False

    def build_return_colors(self):
        """Build the ReturnColors .NET project"""
        # Use Patch directory from .AffinityLinux
        patch_dir = Path(self.directory) / "Patch"
        # ReturnColors is downloaded from GitHub, so it's in return-affinity-colors/ReturnColors/
        returncolors_repo_dir = patch_dir / "return-affinity-colors"
        returncolors_dir = returncolors_repo_dir / "ReturnColors"

        # Also check the old location for backwards compatibility
        if not returncolors_dir.exists():
            old_returncolors_dir = patch_dir / "ReturnColors"
            if old_returncolors_dir.exists():
                returncolors_dir = old_returncolors_dir

        if not returncolors_dir.exists():
            self.log(f"ReturnColors directory not found: {returncolors_dir}", "warning")
            self.log("Attempting to download ReturnColors from GitHub...", "info")
            # Try to ensure it's downloaded
            self.ensure_patcher_files(silent=True)
            # Check again after download attempt
            returncolors_repo_dir = patch_dir / "return-affinity-colors"
            returncolors_dir = returncolors_repo_dir / "ReturnColors"
            if not returncolors_dir.exists():
                old_returncolors_dir = patch_dir / "ReturnColors"
                if old_returncolors_dir.exists():
                    returncolors_dir = old_returncolors_dir
            if not returncolors_dir.exists():
                self.log(
                    f"ReturnColors directory still not found after download attempt",
                    "error",
                )
                return None

        csproj_file = returncolors_dir / "ReturnColors.csproj"
        if not csproj_file.exists():
            self.log(f"ReturnColors.csproj not found: {csproj_file}", "warning")
            return None

        self.log(f"Building ReturnColors from: {returncolors_dir}", "info")

        # Build the project
        output_dir = returncolors_dir / "bin" / "Release"
        success, stdout, stderr = self.run_command(
            [
                "dotnet",
                "build",
                str(csproj_file),
                "-c",
                "Release",
                "-o",
                str(output_dir),
            ],
            check=False,
            capture=True,
        )

        if not success:
            self.log(f"Failed to build ReturnColors: {stderr}", "warning")
            if stdout:
                self.log(f"Build output: {stdout}", "warning")
            return None

        # Find the built executable
        possible_names = [
            "ReturnColors",  # Native executable (Linux)
            "ReturnColors.dll",  # DLL (runnable with dotnet)
            "ReturnColors.exe",  # Windows executable (unlikely on Linux)
        ]

        returncolors_exe = None
        for name in possible_names:
            candidate = output_dir / name
            if candidate.exists():
                returncolors_exe = candidate
                break

        if returncolors_exe and returncolors_exe.exists():
            self.log(f"ReturnColors built successfully: {returncolors_exe}", "success")
            return returncolors_exe
        else:
            if output_dir.exists():
                files = list(output_dir.glob("*"))
                self.log(
                    f"Files in output directory: {[f.name for f in files]}", "warning"
                )
            self.log(
                f"Built ReturnColors not found at expected location: {output_dir}",
                "warning",
            )
            return None

    def run_return_colors_colorize(self, affinity_dir):
        """Run ReturnColors colorize command to restore colored icons"""
        if not Path(affinity_dir).exists():
            self.log(f"Affinity directory not found: {affinity_dir}", "warning")
            return False

        # Build ReturnColors if needed
        returncolors_exe = self.build_return_colors()
        if not returncolors_exe:
            self.log("ReturnColors not available, skipping icon colorization", "info")
            return False

        self.log("Running ReturnColors to restore colored icons...", "info")

        # Run ReturnColors colorize command
        # The command expects: colorize <directory>
        if returncolors_exe.suffix == ".dll":
            cmd = ["dotnet", str(returncolors_exe), "colorize", str(affinity_dir)]
        else:
            cmd = [str(returncolors_exe), "colorize", str(affinity_dir)]

        success, stdout, stderr = self.run_command(cmd, check=False, capture=True)

        if success:
            self.log("ReturnColors colorize completed successfully", "success")
            if stdout:
                # Log the output
                for line in stdout.strip().split("\n"):
                    if line.strip():
                        if "success" in line.lower() or "completed" in line.lower():
                            self.log(line, "success")
                        elif "error" in line.lower() or "failed" in line.lower():
                            self.log(line, "error")
                        else:
                            self.log(line, "info")
            return True
        else:
            self.log(f"ReturnColors colorize failed: {stderr}", "warning")
            if stdout:
                self.log(f"Output: {stdout}", "warning")
            return False

    def patch_affinity_dll(self, app_name):
        """Patch the Serif.Affinity.dll for Affinity v3 (Unified)"""
        # Only patch Affinity v3 (Unified)
        if app_name != "Add" and app_name != "Affinity (Unified)":
            return True  # Not applicable, return success

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Patching Affinity DLL for settings fix...", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Ensure patcher files (including ReturnColors) are available
        self.ensure_patcher_files(silent=True)

        # Check if .NET SDK is available, try to install if missing
        if not self.check_dotnet_sdk():
            self.log(".NET SDK not found. Attempting to install...", "info")
            if not self.install_dotnet_sdk():
                self.log("Failed to install .NET SDK automatically", "warning")
                self.log("Settings patching will be skipped.", "warning")
                self.log("You can install .NET SDK manually:", "info")
                if self.distro in ["arch", "cachyos"]:
                    self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                elif self.distro in ["endeavouros", "xerolinux"]:
                    self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                elif self.distro in ["fedora", "nobara"]:
                    self.log("  sudo dnf install dotnet-sdk-8.0", "info")
                elif self.distro in ["pikaos", "pop", "debian"]:
                    self.log("  sudo apt install dotnet-sdk-8.0", "info")
                    self.log("  (May require Microsoft's .NET repository)", "warning")
                elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                    self.log("  sudo zypper install dotnet-sdk-8.0", "info")
                return False
            else:
                self.log(".NET SDK installed successfully", "success")

        # Find the DLL
        dll_path = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / "Affinity"
            / "Serif.Affinity.dll"
        )

        if not dll_path.exists():
            self.log(f"Serif.Affinity.dll not found at: {dll_path}", "warning")
            self.log(
                "The DLL may not be installed yet. Patching will be skipped.", "warning"
            )
            return False

        # Run the settings patcher
        result = self.run_affinity_patcher(str(dll_path))

        # Also apply SharedStorageAccessManager fix for OAuth support
        self.ensure_ssa_fix_files(silent=True)
        self.run_ssa_fix(str(dll_path))

        return result

    def create_desktop_entry(self, app_name):
        """Create desktop entry for application"""
        app_names = {
            "Photo": ("Photo", "Photo.exe", "Photo 2", "AffinityPhoto.svg"),
            "Designer": (
                "Designer",
                "Designer.exe",
                "Designer 2",
                "AffinityDesigner.svg",
            ),
            "Publisher": (
                "Publisher",
                "Publisher.exe",
                "Publisher 2",
                "AffinityPublisher.svg",
            ),
            "Add": ("Affinity", "Affinity.exe", "Affinity", "Affinity.svg"),
        }

        name, exe, dir_name, icon = app_names.get(
            app_name, ("Affinity", "Affinity.exe", "Affinity", "Affinity.svg")
        )

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = desktop_dir / f"Affinity{name}.desktop"
        if app_name == "Add":
            desktop_file = desktop_dir / "Affinity.desktop"

        wine = self.get_wine_path("wine")
        app_path = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / dir_name
            / exe
        )
        icon_path = Path.home() / ".local" / "share" / "icons" / icon

        # Normalize all paths to strings to avoid double slashes
        wine_str = str(wine)
        directory_str = str(self.directory).rstrip(
            "/"
        )  # Remove trailing slash if present
        icon_path_str = str(icon_path)
        app_path_str = str(app_path).replace(
            "\\", "/"
        )  # Ensure forward slashes, no double slashes

        # Get GPU environment variables if configured
        gpu_env = self.get_gpu_env_vars()
        # Get DXVK environment variables if AMD GPU is detected
        dxvk_env = self.get_dxvk_env_vars()

        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\n")
            if app_name == "Add":
                f.write("Name=Affinity Suite\n")
                f.write("Comment=A powerful creative suite.\n")
            else:
                f.write(f"Name=Affinity {name}\n")
                f.write(f"Comment=A powerful {name.lower()} software.\n")
            f.write(f"Icon={icon_path_str}\n")
            f.write(f"Path={directory_str}\n")
            # Use Linux path format with proper quoting for spaces
            # Include GPU environment variables if configured
            exec_line = f"Exec=env WINEPREFIX={directory_str}"
            if gpu_env:
                exec_line += f" {gpu_env}"
            if dxvk_env:
                exec_line += f" {dxvk_env}"
            exec_line += f' {wine_str} "{app_path_str}"'
            f.write(f"{exec_line}\n")
            f.write("Terminal=false\n")
            f.write("Type=Application\n")
            f.write("Categories=Graphics;\n")
            f.write("StartupNotify=true\n")
            if app_name == "Add":
                f.write("StartupWMClass=affinity.exe\n")
            else:
                f.write(f"StartupWMClass={name.lower()}.exe\n")

        # Remove Wine's default entry
        wine_entry = desktop_dir / "wine" / "Programs" / f"Affinity {name} 2.desktop"
        if wine_entry.exists():
            wine_entry.unlink()

        if app_name == "Add":
            wine_entry = desktop_dir / "wine" / "Programs" / "Affinity.desktop"
            if wine_entry.exists():
                wine_entry.unlink()

        # Remove duplicate wine-protocol-affinity.desktop file
        wine_protocol_entry = desktop_dir / "wine-protocol-affinity.desktop"
        if wine_protocol_entry.exists():
            try:
                wine_protocol_entry.unlink()
                self.log("Removed duplicate wine-protocol-affinity.desktop", "info")
            except Exception as e:
                self.log(
                    f"Warning: Could not remove wine-protocol-affinity.desktop: {e}",
                    "warning",
                )

        # Create desktop shortcut
        desktop_shortcut = Path.home() / "Desktop" / desktop_file.name
        if desktop_shortcut.parent.exists():
            try:
                shutil.copy2(desktop_file, desktop_shortcut)
                self.log("Desktop shortcut created", "success")
            except PermissionError:
                self.log(
                    f"Could not create desktop shortcut (permission denied): {desktop_shortcut}",
                    "warning",
                )
                self.log(
                    "Desktop entry is still available in the applications menu", "info"
                )
            except Exception as e:
                self.log(f"Could not create desktop shortcut: {e}", "warning")

        self.log(f"Desktop entry created: {desktop_file}", "success")

    def _download_affinity_installer_thread(self, save_path_obj: Path):
        """Worker: Download Affinity installer and end operation."""
        download_url = "https://downloads.affinity.studio/Affinity%20x64.exe"
        self.log(f"Downloading from: {download_url}", "info")
        self.log(f"Saving to: {save_path_obj}", "info")
        try:
            if self.download_file(
                download_url, str(save_path_obj), "Affinity installer"
            ):
                self.log(f"\n✓ Download completed successfully!", "success")
                self.log(f"Installer saved to: {save_path_obj}", "success")
                self.show_message(
                    "Download Complete",
                    "Affinity installer has been downloaded successfully!\n\nYou can now run it with the installer buttons.",
                    "info",
                )
            else:
                self.log("✗ Download failed", "error")
        finally:
            self.end_operation()

    def open_winecfg(self):
        """Open Wine Configuration tool using custom Wine"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Opening Wine Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        wine_cfg = self.get_wine_path("winecfg")

        if not wine_cfg.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        self.log(f"Opening winecfg using: {wine_cfg}", "info")
        self.log("The Wine Configuration window should open now.", "info")

        # Run winecfg in background (non-blocking)
        threading.Thread(
            target=lambda: self.run_command(
                [str(wine_cfg)], check=False, capture=False, env=env
            ),
            daemon=True,
        ).start()

        self.log("✓ Wine Configuration opened", "success")

    def open_winetricks(self):
        """Open Winetricks GUI using custom Wine"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Opening Winetricks", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        wine_cfg = self.get_wine_path("winecfg")

        if not wine_cfg.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # Check if winetricks is available
        winetricks_path = shutil.which("winetricks")
        if not winetricks_path:
            self.log(
                "Winetricks is not installed. Please install it using your package manager.",
                "error",
            )
            self.show_message(
                "Winetricks Not Found",
                "Winetricks is not installed. Please install it using:\n\n"
                "Arch/CachyOS/EndeavourOS/XeroLinux: sudo pacman -S winetricks\n"
                "Fedora/Nobara: sudo dnf install winetricks\n"
                "Debian/Ubuntu/Mint/Pop/Zorin/PikaOS: sudo apt install winetricks\n"
                "openSUSE: sudo zypper install winetricks",
                "error",
            )
            return

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        self.log(f"Opening winetricks using: {winetricks_path}", "info")
        self.log("The Winetricks GUI should open now.", "info")

        # Run winetricks in background (non-blocking)
        # Winetricks will open its GUI when run without arguments
        threading.Thread(
            target=lambda: self.run_command(
                [winetricks_path], check=False, capture=False, env=env
            ),
            daemon=True,
        ).start()

        self.log("✓ Winetricks opened", "success")

    def set_windows11_renderer(self):
        """Set Windows 11 and configure renderer (OpenGL or Vulkan)"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Windows 11 + Renderer Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Start operation for renderer configuration
        self.start_operation("Configure Renderer")

        wine_cfg = self.get_wine_path("winecfg")

        if not wine_cfg.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.end_operation()
            return

        # Ask user to choose renderer (without parent to avoid threading issues)
        dialog = QDialog()
        dialog.setWindowTitle("Select Renderer")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(350, int(screen_width * 0.9))
            min_height = min(280, int(screen_height * 0.7))
            default_width = min(450, int(screen_width * 0.85))
            default_height = min(320, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 400
            min_height = 300
            default_width = 500
            default_height = 350
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 400
            min_height = 300
            default_width = 500
            default_height = 350
            max_width = 750
            max_height = 600

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet matching main UI
        if self.dark_mode:
            dialog_style = """
                QDialog {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed {
                    background-color: #3db9a0;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #2d2d2d;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #666666;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        else:
            dialog_style = """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 12px;
                    color: #666666;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 14px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#okButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#okButton:pressed {
                    background-color: #3d8b40;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """

        dialog.setStyleSheet(dialog_style)

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("Select Renderer")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel("Choose a renderer for troubleshooting:")
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        button_group = QButtonGroup()

        # Vulkan option
        vulkan_frame = QFrame()
        vulkan_frame.setObjectName("optionFrame")
        vulkan_layout = QVBoxLayout(vulkan_frame)
        vulkan_layout.setContentsMargins(12, 10, 12, 10)
        vulkan_radio = QRadioButton("Vulkan (Recommended - OpenCL support)")
        vulkan_radio.setChecked(True)
        vulkan_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        vulkan_layout.addWidget(vulkan_radio)
        options_layout.addWidget(vulkan_frame)

        # OpenGL option
        opengl_frame = QFrame()
        opengl_frame.setObjectName("optionFrame")
        opengl_layout = QVBoxLayout(opengl_frame)
        opengl_layout.setContentsMargins(12, 10, 12, 10)
        opengl_radio = QRadioButton("OpenGL (Alternative)")
        opengl_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        opengl_layout.addWidget(opengl_radio)
        options_layout.addWidget(opengl_frame)

        # GDI option
        gdi_frame = QFrame()
        gdi_frame.setObjectName("optionFrame")
        gdi_layout = QVBoxLayout(gdi_frame)
        gdi_layout.setContentsMargins(12, 10, 12, 10)
        gdi_radio = QRadioButton("GDI (Fallback)")
        gdi_radio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        gdi_layout.addWidget(gdi_radio)
        options_layout.addWidget(gdi_frame)

        button_group.addButton(vulkan_radio, 0)
        button_group.addButton(opengl_radio, 1)
        button_group.addButton(gdi_radio, 2)

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.log("Renderer configuration cancelled", "warning")
            self.end_operation()
            return

        # Determine selected renderer
        renderer_map = {
            0: ("vulkan", "Vulkan"),
            1: ("opengl", "OpenGL"),
            2: ("gdi", "GDI"),
        }

        selected_id = button_group.checkedId()
        renderer_value, renderer_name = renderer_map.get(
            selected_id, ("vulkan", "Vulkan")
        )

        # Ensure wine-tkg is available for winetricks (fallback method)
        self.log("Setting up wine-tkg for winetricks (if needed)...", "info")
        self.ensure_wine_tkg()  # Don't fail if this doesn't work, it's just a fallback

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        # Use wine-tkg for winetricks if available (fallback method)
        env = self.get_winetricks_env_with_tkg(env)

        # Set Windows version to 11
        self.log("Setting Windows version to 11...", "info")
        success, _, _ = self.run_command(
            [str(wine_cfg), "-v", "win11"], check=False, env=env
        )
        if success:
            self.log("✓ Windows version set to 11", "success")
        else:
            self.log("⚠ Warning: Failed to set Windows version", "warning")

        # Set renderer directly via registry (more reliable than winetricks)
        self.log(f"Configuring {renderer_name} renderer...", "info")
        wine = self.get_wine_path("wine")

        # Set renderer directly via registry - this is more reliable than winetricks
        self.log(f"Setting {renderer_name} renderer via registry...", "info")
        reg_add_success, reg_add_stdout, reg_add_stderr = self.run_command(
            [
                str(wine),
                "reg",
                "add",
                "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                "/v",
                "renderer",
                "/t",
                "REG_SZ",
                "/d",
                renderer_value,
                "/f",
            ],
            check=False,
            env=env,
            capture=True,
        )

        if reg_add_success:
            self.log(f"✓ {renderer_name} renderer set via registry", "success")
        else:
            # Fallback to winetricks if direct registry setting fails
            self.log(f"Registry method failed, trying winetricks...", "info")
            success, stdout, stderr = self.run_command(
                [
                    "winetricks",
                    "--unattended",
                    "--force",
                    "--no-isolate",
                    "--optout",
                    f"renderer={renderer_value}",
                ],
                check=False,
                env=env,
            )
            if success:
                self.log(f"✓ {renderer_name} renderer set via winetricks", "success")
            else:
                self.log(
                    f"⚠ Warning: Failed to set {renderer_name} renderer via both methods",
                    "warning",
                )

        # Verify renderer was actually set in registry
        self.log(f"Verifying {renderer_name} renderer configuration...", "info")
        renderer_verified = False

        try:
            # Check registry for renderer setting
            renderer_check_success, renderer_check_stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                    "/v",
                    "renderer",
                ],
                check=False,
                env=env,
                capture=True,
            )

            if renderer_check_success and renderer_check_stdout:
                renderer_check_lower = renderer_check_stdout.lower()
                # Check for the renderer value we set
                if renderer_value == "vulkan" and "vulkan" in renderer_check_lower:
                    renderer_verified = True
                elif renderer_value == "opengl" and "opengl" in renderer_check_lower:
                    renderer_verified = True
                elif renderer_value == "gdi" and "gdi" in renderer_check_lower:
                    renderer_verified = True

                if renderer_verified:
                    self.log(
                        f"✓ {renderer_name} renderer verified in registry", "success"
                    )
                else:
                    # Show what was actually found
                    actual_renderer = None
                    if "renderer" in renderer_check_lower:
                        # Extract the actual value
                        match = re.search(
                            r"renderer\s+REG_SZ\s+(\w+)",
                            renderer_check_stdout,
                            re.IGNORECASE,
                        )
                        if match:
                            actual_renderer = match.group(1)
                            self.log(
                                f"⚠ Warning: Expected {renderer_name} but found {actual_renderer} in registry",
                                "warning",
                            )
                        else:
                            self.log(
                                f"⚠ Warning: {renderer_name} renderer may not be set correctly",
                                "warning",
                            )
                    else:
                        self.log(
                            f"⚠ Warning: Could not verify {renderer_name} renderer in registry",
                            "warning",
                        )

                    # Retry setting the renderer if verification failed
                    if (
                        not actual_renderer
                        or actual_renderer.lower() != renderer_value.lower()
                    ):
                        self.log(
                            f"Retrying to set {renderer_name} renderer via registry...",
                            "info",
                        )
                        retry_success, _, retry_stderr = self.run_command(
                            [
                                str(wine),
                                "reg",
                                "add",
                                "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                                "/v",
                                "renderer",
                                "/t",
                                "REG_SZ",
                                "/d",
                                renderer_value,
                                "/f",
                            ],
                            check=False,
                            env=env,
                            capture=True,
                        )

                        if retry_success:
                            # Verify again after retry
                            verify_success, verify_stdout, _ = self.run_command(
                                [
                                    str(wine),
                                    "reg",
                                    "query",
                                    "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                                    "/v",
                                    "renderer",
                                ],
                                check=False,
                                env=env,
                                capture=True,
                            )

                            if (
                                verify_success
                                and renderer_value.lower()
                                in (verify_stdout or "").lower()
                            ):
                                self.log(
                                    f"✓ {renderer_name} renderer set successfully via registry",
                                    "success",
                                )
                            else:
                                self.log(
                                    f"⚠ Warning: Failed to verify {renderer_name} renderer after retry",
                                    "warning",
                                )
                        else:
                            self.log(
                                f"⚠ Warning: Failed to set {renderer_name} renderer via registry: {retry_stderr[:100] if retry_stderr else 'Unknown error'}",
                                "warning",
                            )
            else:
                self.log(f"⚠ Warning: Could not read renderer from registry", "warning")
        except Exception as e:
            self.log(f"⚠ Warning: Error verifying renderer: {e}", "warning")

        self.log("\n✓ Windows 11 and renderer configuration completed", "success")
        self.end_operation()

    def install_dotnet_sdk(self, version="8.0"):
        """Install .NET SDK based on distribution"""
        try:
            self.log(f"Installing .NET SDK {version}...", "info")

            # Determine package name based on version
            if version == "10.0":
                package_name = "dotnet-sdk-10.0"
            else:
                package_name = "dotnet-sdk-8.0"

            if self.distro in [
                "pikaos",
                "pop",
                "debian",
                "ubuntu",
                "linuxmint",
                "zorin",
            ]:
                # Try installing dotnet-sdk (may need Microsoft repo)
                success, _, stderr = self.run_command(
                    ["sudo", "apt", "install", "-y", package_name], check=False
                )
                if not success:
                    self.log(
                        f"Failed to install {package_name} from default repos",
                        "warning",
                    )
                    self.log(
                        "You may need to add Microsoft's .NET repository. See: https://learn.microsoft.com/dotnet/core/install/linux",
                        "info",
                    )
                    return False
                return True

            commands = {
                "arch": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "cachyos": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "endeavouros": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "xerolinux": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "fedora": ["sudo", "dnf", "install", "-y", package_name],
                "nobara": ["sudo", "dnf", "install", "-y", package_name],
                "opensuse-tumbleweed": [
                    "sudo",
                    "zypper",
                    "install",
                    "-y",
                    package_name,
                ],
                "opensuse-leap": ["sudo", "zypper", "install", "-y", package_name],
            }

            if self.distro in commands:
                success, _, stderr = self.run_command(
                    commands[self.distro], check=False
                )
                if success:
                    self.log(".NET SDK installed successfully", "success")
                    return True
                else:
                    self.log(
                        f"Failed to install .NET SDK: {stderr[:200] if stderr else 'Unknown error'}",
                        "error",
                    )
                    return False

            self.log(
                f"Unsupported distribution for .NET SDK auto-install: {self.format_distro_name()}",
                "error",
            )
            return False
        except Exception as e:
            self.log(f"Error installing .NET SDK: {e}", "error")
            return False

    def apply_return_colors(self):
        """Apply ReturnColors patch to restore colored icons in Affinity v3"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Return Colors (Affinity v3)", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please setup Wine environment first.", "error"
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before applying patches.\n"
                "Please setup Wine environment first.",
            )
            return

        # Check if Affinity v3 is installed
        affinity_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        dll_path = affinity_dir / "Serif.Affinity.dll"

        if not dll_path.exists():
            self.log("Affinity v3 (Unified) is not installed.", "error")
            self.log(f"Expected DLL at: {dll_path}", "info")
            self.show_message(
                "Affinity v3 Not Found",
                "Affinity v3 (Unified) is not installed.\n\n"
                "This patch only works for Affinity v3 (Unified).\n"
                "Please install Affinity v3 first using the 'Affinity (Unified)' button.",
                "error",
            )
            return

        self.start_operation("Return Colors")

        # Ensure patcher files are available
        self.ensure_patcher_files()

        # Check if .NET SDK 10.0+ is installed (required for ReturnColors)
        if not self.check_dotnet_sdk_10():
            self.log(".NET SDK 10.0+ is required for ReturnColors patch", "warning")
            self.log("Attempting to install .NET SDK 10.0 automatically...", "info")

            # Try to install dotnet-sdk-10.0 automatically
            install_success = False
            if self.distro in [
                "pikaos",
                "pop",
                "debian",
                "ubuntu",
                "linuxmint",
                "zorin",
            ]:
                success, _, _ = self.run_command(
                    ["sudo", "apt", "install", "-y", "dotnet-sdk-10.0"], check=False
                )
                if success:
                    install_success = True
                else:
                    self.log(
                        "Failed to install dotnet-sdk-10.0 from default repos",
                        "warning",
                    )
            elif self.distro in ["arch", "cachyos"]:
                success, _, _ = self.run_command(
                    [
                        "sudo",
                        "pacman",
                        "-S",
                        "--needed",
                        "--noconfirm",
                        "dotnet-sdk-10.0",
                    ],
                    check=False,
                )
                if success:
                    install_success = True
            elif self.distro in ["endeavouros", "xerolinux"]:
                success, _, _ = self.run_command(
                    [
                        "sudo",
                        "pacman",
                        "-S",
                        "--needed",
                        "--noconfirm",
                        "dotnet-sdk-10.0",
                    ],
                    check=False,
                )
                if success:
                    install_success = True
            elif self.distro in ["fedora", "nobara"]:
                success, _, _ = self.run_command(
                    ["sudo", "dnf", "install", "-y", "dotnet-sdk-10.0"], check=False
                )
                if success:
                    install_success = True
            elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                success, _, _ = self.run_command(
                    ["sudo", "zypper", "install", "-y", "dotnet-sdk-10.0"], check=False
                )
                if success:
                    install_success = True

            # Check again if installation succeeded
            if install_success and self.check_dotnet_sdk_10():
                self.log(".NET SDK 10.0 installed successfully", "success")
            else:
                # Installation failed or still not detected, show manual instructions
                self.log(".NET SDK 10.0+ is required for ReturnColors patch", "error")
                self.log(
                    "ReturnColors requires .NET SDK 10.0 or newer to build.", "info"
                )
                self.log("Please install .NET SDK 10.0 manually:", "info")

                install_instructions = ""
                if self.distro in ["arch", "cachyos"]:
                    self.log("  sudo pacman -S dotnet-sdk-10.0", "info")
                    install_instructions = "sudo pacman -S dotnet-sdk-10.0"
                elif self.distro in ["endeavouros", "xerolinux"]:
                    self.log("  sudo pacman -S dotnet-sdk-10.0", "info")
                    install_instructions = "sudo pacman -S dotnet-sdk-10.0"
                elif self.distro in ["fedora", "nobara"]:
                    self.log("  sudo dnf install dotnet-sdk-10.0", "info")
                    install_instructions = "sudo dnf install dotnet-sdk-10.0"
                elif self.distro in [
                    "pikaos",
                    "pop",
                    "debian",
                    "ubuntu",
                    "linuxmint",
                    "zorin",
                ]:
                    self.log("  sudo apt install dotnet-sdk-10.0", "info")
                    self.log("  (May require Microsoft's .NET repository)", "warning")
                    install_instructions = "sudo apt install dotnet-sdk-10.0\n(May require Microsoft's .NET repository)"
                elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                    self.log("  sudo zypper install dotnet-sdk-10.0", "info")
                    install_instructions = "sudo zypper install dotnet-sdk-10.0"
                else:
                    self.log(
                        "  Please install .NET SDK 10.0 from: https://dotnet.microsoft.com/download",
                        "info",
                    )
                    install_instructions = (
                        "Install from: https://dotnet.microsoft.com/download"
                    )

                # Ensure distro is detected before trying alternative method
                if not self.distro:
                    self.detect_distro()

                # Try to install using the install_dotnet_sdk method as fallback
                self.log(
                    "Attempting to install .NET SDK using alternative method...", "info"
                )
                if self.install_dotnet_sdk(version="10.0"):
                    # Check again if installation succeeded
                    if self.check_dotnet_sdk_10():
                        self.log(
                            ".NET SDK 10.0 installed successfully via alternative method",
                            "success",
                        )
                    else:
                        self.end_operation()
                        self.show_message(
                            ".NET SDK 10.0 Required",
                            "ReturnColors patch requires .NET SDK 10.0 or newer to build.\n\n"
                            f"Please install it manually:\n{install_instructions}\n\n"
                            "After installing, restart the installer and try again.",
                            "error",
                        )
                        return
                else:
                    self.end_operation()
                    self.show_message(
                        ".NET SDK 10.0 Required",
                        "ReturnColors patch requires .NET SDK 10.0 or newer to build.\n\n"
                        f"Please install it manually:\n{install_instructions}\n\n"
                        "After installing, restart the installer and try again.",
                        "error",
                    )
                    return

        # Run ReturnColors colorize
        success = self.run_return_colors_colorize(str(affinity_dir))

        if success:
            self.log("\n✓ ReturnColors patch applied successfully!", "success")
            self.log(
                "Affinity v3 icons have been restored to colored versions.", "info"
            )
            self.end_operation()
            self.show_message(
                "Patch Applied Successfully",
                "ReturnColors patch has been applied successfully!\n\n"
                "Affinity v3 icons have been restored to colored versions.\n"
                "You may need to restart Affinity v3 to see the changes.",
                "info",
            )
        else:
            self.log("\n✗ ReturnColors patch failed", "error")
            self.end_operation()
            self.show_message(
                "Patch Failed",
                "Failed to apply ReturnColors patch.\n\n"
                "Please check the log for details and ensure:\n"
                "• Affinity v3 is installed\n"
                "• .NET SDK is installed\n"
                "• ReturnColors files are available",
                "error",
            )

    def fix_affinity_settings(self):
        """Fix Affinity v3 settings by patching the DLL"""
        try:
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Fix Affinity v3 Settings", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Ensure patcher files are available
            self.ensure_patcher_files()

            # Check if Affinity v3 is installed
            dll_path = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / "Affinity"
                / "Serif.Affinity.dll"
            )

            if not dll_path.exists():
                self.log("Affinity v3 (Unified) is not installed.", "error")
                self.log(f"Expected DLL at: {dll_path}", "info")
                self.show_message(
                    "Affinity v3 Not Found",
                    "Affinity v3 (Unified) is not installed.\n\n"
                    "This fix only works for Affinity v3 (Unified).\n"
                    "Please install Affinity v3 first using the 'Affinity (Unified)' button.",
                    "error",
                )
                return

            self.start_operation("Fix Affinity Settings")

            # Check if .NET SDK is installed, if not try to install it
            if not self.check_dotnet_sdk():
                self.log(".NET SDK not found. Attempting to install...", "info")
                try:
                    if not self.install_dotnet_sdk():
                        self.log("Failed to install .NET SDK automatically", "error")
                        self.log("Please install .NET SDK manually:", "info")
                        if self.distro in ["arch", "cachyos"]:
                            self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                        elif self.distro in ["endeavouros", "xerolinux"]:
                            self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                        elif self.distro in ["fedora", "nobara"]:
                            self.log("  sudo dnf install dotnet-sdk-8.0", "info")
                        elif self.distro in ["pikaos", "pop", "debian"]:
                            self.log("  sudo apt install dotnet-sdk-8.0", "info")
                            self.log(
                                "  (May require Microsoft's .NET repository)", "warning"
                            )
                        elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                            self.log("  sudo zypper install dotnet-sdk-8.0", "info")
                        self.end_operation()
                        self.show_message(
                            ".NET SDK Required",
                            ".NET SDK is required to patch the Affinity DLL.\n\n"
                            "Please install it manually using the commands shown in the log, then try again.",
                            "error",
                        )
                        return
                except Exception as e:
                    self.log(f"Error during .NET SDK installation: {e}", "error")
                    self.end_operation()
                    self.show_message(
                        "Installation Error",
                        f"An error occurred while trying to install .NET SDK:\n{e}\n\n"
                        "Please install .NET SDK manually and try again.",
                        "error",
                    )
                    return

            # Patch the DLL
            success = self.patch_affinity_dll("Add")

            if success:
                self.log("\n✓ Settings fix completed successfully!", "success")
                self.log(
                    "Affinity v3 should now be able to save settings properly.", "info"
                )
                self.log(
                    "You may need to restart Affinity for the changes to take effect.",
                    "info",
                )
                self.show_message(
                    "Settings Fix Complete",
                    "The Affinity v3 DLL has been patched successfully!\n\n"
                    "Settings should now save properly.\n"
                    "You may need to restart Affinity for the changes to take effect.",
                    "info",
                )
            else:
                self.log("\n✗ Settings fix failed", "error")
                self.show_message(
                    "Settings Fix Failed",
                    "Failed to patch the Affinity v3 DLL.\n\n"
                    "Please check the log for details.\n"
                    "Make sure .NET SDK is installed if you see related errors.",
                    "error",
                )
        except Exception as e:
            self.log(f"Unexpected error during settings fix: {e}", "error")
            self.show_message(
                "Unexpected Error",
                f"An unexpected error occurred:\n{e}\n\n"
                "Please check the log for details.",
                "error",
            )
        finally:
            self.end_operation()

    def set_dpi_scaling(self):
        """Set DPI scaling for Affinity applications"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("DPI Scaling Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        wine = self.get_wine_path("wine")

        if not wine.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # Try to get current DPI value from registry
        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        current_dpi = 96  # Default value

        # Try to read current DPI from registry
        try:
            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Control Panel\\Desktop",
                    "/v",
                    "LogPixels",
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success and stdout:
                # Parse the output to extract DPI value
                # Output format: "LogPixels    REG_DWORD    0x000000c0 (192)"
                match = re.search(r"0x[0-9a-fA-F]+|(\d+)", stdout)
                if match:
                    # Try to find hex value first
                    hex_match = re.search(r"0x([0-9a-fA-F]+)", stdout)
                    if hex_match:
                        current_dpi = int(hex_match.group(1), 16)
                    else:
                        # Try decimal
                        dec_match = re.search(r"\((\d+)\)", stdout)
                        if dec_match:
                            current_dpi = int(dec_match.group(1))
        except:
            pass  # Use default if reading fails

        # Create dialog (without parent to avoid threading issues)
        dialog = QDialog()
        dialog.setWindowTitle("Set DPI Scaling")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(350, int(screen_height * 0.7))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(400, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 450
            min_height = 380
            default_width = 550
            default_height = 420
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 450
            min_height = 380
            default_width = 550
            default_height = 420
            max_width = 800
            max_height = 700

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("Set DPI Scaling")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Info label
        info_label = QLabel(
            "Adjust DPI scaling for Affinity applications.\n"
            "Higher values make UI elements larger.\n\n"
            "Common values:\n"
            "• 96 = 100% (1080p, 24-27 inches)\n"
            "• 120 = 125% (1080p, 13-15 inch laptops)\n"
            "• 144 = 150% (1440p, 27-32 inches)\n"
            "• 192 = 200% (4K, 27-32 inches)"
        )
        info_label.setObjectName("descriptionLabel")
        info_label.setWordWrap(True)
        info_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(info_label)

        # Current value display
        value_label = QLabel()
        value_label.setObjectName("titleLabel")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(value_label)

        # Slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(96)
        slider.setMaximum(480)
        slider.setValue(current_dpi)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(24)  # Show ticks every 24 DPI
        slider.setSingleStep(12)  # Step by 12 DPI for smoother adjustment
        slider.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        main_layout.addWidget(slider)

        # Min/Max labels
        minmax_layout = QHBoxLayout()
        min_label = QLabel("96 (100%)")
        min_label.setObjectName("descriptionLabel")
        minmax_layout.addWidget(min_label)
        minmax_layout.addStretch()
        max_label = QLabel("480 (500%)")
        max_label.setObjectName("descriptionLabel")
        minmax_layout.addWidget(max_label)
        main_layout.addLayout(minmax_layout)

        # Update label when slider changes
        def update_label(value):
            percentage = int((value / 96) * 100)
            value_label.setText(f"DPI: {value} ({percentage}%)")

        slider.valueChanged.connect(update_label)
        update_label(current_dpi)  # Set initial value

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("okButton")
        save_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        save_btn.setDefault(True)
        save_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(save_btn)

        main_layout.addLayout(button_layout)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.log("DPI scaling configuration cancelled", "warning")
            return

        selected_dpi = slider.value()
        percentage = int((selected_dpi / 96) * 100)

        # Apply DPI setting via registry
        self.log(f"Setting DPI scaling to {selected_dpi} ({percentage}%)...", "info")

        # Use wine reg add command
        success, stdout, stderr = self.run_command(
            [
                str(wine),
                "reg",
                "add",
                "HKEY_CURRENT_USER\\Control Panel\\Desktop",
                "/v",
                "LogPixels",
                "/t",
                "REG_DWORD",
                "/d",
                str(selected_dpi),
                "/f",
            ],
            check=False,
            env=env,
        )

        if success:
            self.log(f"✓ DPI scaling set to {selected_dpi} ({percentage}%)", "success")
            self.log(
                "Note: You may need to restart Affinity applications for the change to take effect.",
                "info",
            )
            self.show_message(
                "DPI Scaling Updated",
                f"DPI scaling has been set to {selected_dpi} ({percentage}%).\n\n"
                "You may need to restart Affinity applications for the change to take effect.",
                "info",
            )
        else:
            self.log(
                f"✗ Failed to set DPI scaling: {stderr or 'Unknown error'}", "error"
            )
            self.show_message(
                "Error",
                f"Failed to set DPI scaling:\n{stderr or 'Unknown error'}",
                "error",
            )

    def uninstall_affinity_linux(self):
        """Uninstall Affinity Linux by deleting the .AffinityLinux folder"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Uninstall Affinity Linux", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Show warning dialog with Yes/No buttons
        reply = QMessageBox.warning(
            self,
            "Uninstall Affinity Linux",
            "WARNING: This will permanently delete the .AffinityLinux folder and all its contents.\n\n"
            "This includes:\n"
            "• All Wine configuration and settings\n"
            "• All installed Affinity applications (Photo, Designer, Publisher, Unified)\n"
            "• All application data and preferences\n"
            "• All downloaded installers and cached files\n"
            "• WebView2 Runtime and other dependencies\n"
            "• Desktop entries from .local/share/applications\n\n"
            "This action CANNOT be undone!\n\n"
            "Do you want to proceed with the uninstall?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            self.log("Uninstall cancelled by user", "warning")
            return

        # Stop Wine processes first
        self.log("Stopping Wine processes...", "info")
        try:
            self.run_command(["wineserver", "-k"], check=False)
            time.sleep(2)
            self.log("Wine processes stopped", "success")
        except Exception as e:
            self.log(f"Warning: Could not stop all Wine processes: {e}", "warning")

        # Remove desktop entries from .local/share/applications
        self.log("Removing desktop entries...", "info")
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_files = [
            desktop_dir / "AffinityPhoto.desktop",
            desktop_dir / "AffinityDesigner.desktop",
            desktop_dir / "AffinityPublisher.desktop",
            desktop_dir / "Affinity.desktop",
        ]

        removed_count = 0
        for desktop_file in desktop_files:
            if desktop_file.exists():
                try:
                    desktop_file.unlink()
                    self.log(f"Removed desktop entry: {desktop_file.name}", "info")
                    removed_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove {desktop_file.name}: {e}", "warning"
                    )

        # Also remove Wine's default entries if they exist
        wine_desktop_dir = desktop_dir / "wine" / "Programs"
        wine_entries = [
            wine_desktop_dir / "Affinity Photo 2.desktop",
            wine_desktop_dir / "Affinity Photo.desktop",
            wine_desktop_dir / "Affinity Designer 2.desktop",
            wine_desktop_dir / "Affinity Designer.desktop",
            wine_desktop_dir / "Affinity Publisher 2.desktop",
            wine_desktop_dir / "Affinity Publisher.desktop",
            wine_desktop_dir / "Affinity.desktop",
        ]

        for wine_entry in wine_entries:
            if wine_entry.exists():
                try:
                    wine_entry.unlink()
                    self.log(f"Removed Wine desktop entry: {wine_entry.name}", "info")
                    removed_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove {wine_entry.name}: {e}", "warning"
                    )

        if removed_count > 0:
            self.log(f"Removed {removed_count} desktop entry/entries", "success")

        # Delete the .AffinityLinux folder
        affinity_dir = Path(self.directory)
        if not affinity_dir.exists():
            self.log(
                "Affinity Linux directory not found. Nothing to uninstall.", "warning"
            )
            self.show_message(
                "Nothing to Uninstall",
                "The .AffinityLinux folder does not exist.\n\nNothing to uninstall.",
                "info",
            )
            return

        self.log(f"Deleting directory: {affinity_dir}", "info")
        try:

            def _force_remove(func, path, exc_info):
                """Error handler: chmod and retry for read-only files"""
                try:
                    os.chmod(path, 0o777)
                    func(path)
                except Exception:
                    pass

            shutil.rmtree(str(affinity_dir), onerror=_force_remove)

            # If rmtree left anything behind, fall back to rm -rf
            if affinity_dir.exists():
                self.log(
                    "Standard removal incomplete, falling back to rm -rf...", "warning"
                )
                result = subprocess.run(
                    ["rm", "-rf", str(affinity_dir)], capture_output=True, text=True
                )
                if result.returncode != 0:
                    raise Exception(f"rm -rf failed: {result.stderr.strip()}")

            self.log("\u2713 .AffinityLinux folder deleted successfully", "success")
            self.log("\n✓ Uninstall completed!", "success")
            self.log("All Affinity Linux files have been removed.", "info")

            self.show_message(
                "Uninstall Complete",
                "The .AffinityLinux folder has been successfully deleted.\n\n"
                "All Affinity installations and configurations have been removed.\n\n"
                "You may close this installer now.",
                "info",
            )

            # Refresh installation status
            QTimer.singleShot(100, self.check_installation_status)

        except PermissionError:
            self.log("✗ Permission denied. Some files may be in use.", "error")
            self.log("Please close all Affinity applications and try again.", "error")
            self.show_message(
                "Uninstall Failed",
                "Permission denied. Some files may be in use.\n\n"
                "Please close all Affinity applications and Wine processes, then try again.",
                "error",
            )
        except Exception as e:
            self.log(f"✗ Failed to delete directory: {e}", "error")
            self.show_message(
                "Uninstall Failed",
                f"Failed to delete the .AffinityLinux folder:\n\n{str(e)}\n\n"
                "You may need to manually delete it.",
                "error",
            )

    # =========================================================================
    # OpenCL GPU Acceleration Patches
    # =========================================================================

    def ensure_opencl_patch_files(self, silent=False):
        """Ensure OpenCL patch files are available in .AffinityLinux/Patch/"""
        try:
            dest_dir = Path(self.directory) / "Patch" / "OpenCLEventCallback"
            prebuilt_dir = dest_dir / "prebuilt"
            dest_dir.mkdir(parents=True, exist_ok=True)
            prebuilt_dir.mkdir(parents=True, exist_ok=True)

            # Files to copy/download
            files_to_get = {
                "prebuilt/opencl.dll": "https://raw.githubusercontent.com/ryzendew/Linux-Affinity-Installer/main/Patch/OpenCLEventCallback/prebuilt/opencl.dll",
            }

            # Try local copy first
            script_dir = Path(__file__).parent
            source_dir = script_dir.parent / "Patch" / "OpenCLEventCallback"

            for filename, github_url in files_to_get.items():
                dest_file = dest_dir / filename
                if dest_file.exists() and dest_file.stat().st_size > 0:
                    continue

                source_file = source_dir / filename
                if source_file.exists():
                    try:
                        shutil.copy2(source_file, dest_file)
                        if not silent:
                            self.log(f"Copied {filename} to Patch/OpenCLEventCallback/", "info")
                        continue
                    except Exception as e:
                        if not silent:
                            self.log(f"Failed to copy {filename} from local: {e}", "warning")

                if not dest_file.exists():
                    if not silent:
                        self.log(f"Downloading {filename} from GitHub...", "info")
                    try:
                        if self.download_file(github_url, str(dest_file), filename):
                            if not silent:
                                self.log(f"Downloaded {filename}", "success")
                        else:
                            if not silent:
                                self.log(f"Failed to download {filename}", "error")
                            return False
                    except Exception as e:
                        if not silent:
                            self.log(f"Error downloading {filename}: {e}", "error")
                        return False

            return True
        except Exception as e:
            if not silent:
                self.log(f"Error ensuring OpenCL patch files: {e}", "error")
            return False

    def install_opencl_dll_patch(self):
        """Install the patched opencl.dll that implements clSetEventCallback"""
        wine_dir = self.get_wine_dir()
        if not wine_dir or not wine_dir.exists():
            self.log("Wine directory not found", "error")
            return False

        opencl_dst = wine_dir / "lib" / "wine" / "x86_64-windows" / "opencl.dll"
        opencl_sys = Path(self.directory) / "drive_c" / "windows" / "system32" / "opencl.dll"
        prebuilt = Path(self.directory) / "Patch" / "OpenCLEventCallback" / "prebuilt" / "opencl.dll"

        if not prebuilt.exists():
            self.log("Pre-built opencl.dll not found", "error")
            return False

        # Check if already installed (same size = likely same file)
        if opencl_dst.exists() and opencl_dst.stat().st_size == prebuilt.stat().st_size:
            self.log("Wine OpenCL patch already installed", "success")
            return True

        # Back up originals
        for dst in [opencl_dst, opencl_sys]:
            if dst.exists():
                backup = dst.with_suffix(".dll.orig")
                if not backup.exists():
                    try:
                        shutil.copy2(dst, backup)
                        self.log(f"Backed up {dst.name} to {backup.name}", "info")
                    except Exception as e:
                        self.log(f"Warning: Could not back up {dst}: {e}", "warning")

        # Install
        try:
            shutil.copy2(prebuilt, opencl_dst)
            self.log("Installed patched opencl.dll to Wine directory", "success")
        except Exception as e:
            self.log(f"Failed to install opencl.dll to Wine: {e}", "error")
            return False

        try:
            shutil.copy2(prebuilt, opencl_sys)
            self.log("Installed patched opencl.dll to system32", "success")
        except Exception as e:
            self.log(f"Warning: Could not copy to system32: {e}", "warning")

        return True

    def run_libraster_patcher(self):
        """Run the libraster.dll binary patcher for OpenCL device discovery bypass"""
        libraster = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / "Affinity"
            / "libraster.dll"
        )

        if not libraster.exists():
            self.log(f"libraster.dll not found at: {libraster}", "warning")
            return False

        # Find the patcher script
        script_dir = Path(__file__).parent
        patcher_script = script_dir / "AffinityOpenCLPatch.sh"

        if not patcher_script.exists():
            # Try from installed location
            patcher_script = Path(self.directory) / "scripts" / "AffinityOpenCLPatch.sh"

        if not patcher_script.exists():
            self.log("AffinityOpenCLPatch.sh not found", "error")
            return False

        self.log("Patching libraster.dll for OpenCL device discovery...", "info")

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        success, stdout, stderr = self.run_command(
            ["bash", str(patcher_script), str(libraster)],
            check=False,
            capture=True,
            env=env,
        )

        if stdout:
            for line in stdout.strip().split("\n"):
                if line.strip():
                    if "[✓]" in line or "success" in line.lower() or "applied" in line.lower():
                        self.log(line.strip(), "success")
                    elif "[ERROR]" in line or "error" in line.lower():
                        self.log(line.strip(), "error")
                    elif "[WARNING]" in line:
                        self.log(line.strip(), "warning")
                    else:
                        self.log(line.strip(), "info")

        if success:
            self.log("libraster.dll OpenCL patches applied", "success")
            return True
        else:
            self.log(f"libraster.dll patching failed: {stderr}", "error")
            return False

    def apply_opencl_patches(self):
        """Apply all OpenCL hardware acceleration patches (UI button handler)"""
        try:
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Patch OpenCL (GPU Acceleration)", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Check Wine is set up
            wine = self.get_wine_path("wine")
            if not wine.exists():
                self.log("Wine is not set up. Please run 'Setup Wine Environment' first.", "error")
                self.show_message(
                    "Wine Not Found",
                    "Wine must be installed before applying OpenCL patches.\n\n"
                    "Please run 'One-Click Setup' or 'Setup Wine Environment' first.",
                    "warning",
                )
                return

            # Check Affinity is installed
            libraster = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / "Affinity"
                / "libraster.dll"
            )
            if not libraster.exists():
                self.log("Affinity is not installed. Please install it first.", "error")
                self.show_message(
                    "Affinity Not Found",
                    "Affinity must be installed before applying OpenCL patches.",
                    "warning",
                )
                return

            self.start_operation("Apply OpenCL Patches")

            def apply_opencl_thread():
                try:
                    self.update_progress(0.0)
                    self.update_progress_text("Downloading OpenCL patch files...")

                    # Step 1: Ensure patch files are available
                    if not self.ensure_opencl_patch_files():
                        self.log("Failed to obtain OpenCL patch files", "error")
                        self.end_operation()
                        return
                    self.update_progress(0.3)

                    # Step 2: Install patched opencl.dll
                    self.update_progress_text("Installing Wine OpenCL patch...")
                    if not self.install_opencl_dll_patch():
                        self.log("Failed to install Wine OpenCL patch", "error")
                        self.end_operation()
                        return
                    self.update_progress(0.6)

                    # Step 3: Patch libraster.dll
                    self.update_progress_text("Patching libraster.dll...")
                    self.run_libraster_patcher()
                    self.update_progress(0.9)

                    # Step 4: Set GPU_DEVICE_ORDINAL hint
                    if self.has_amd_gpu():
                        self.log(
                            "\nNote: On AMD APU+dGPU systems, set GPU_DEVICE_ORDINAL=0 to prevent "
                            "cross-device memory faults. This is configured automatically at launch.",
                            "info",
                        )

                    self.update_progress(1.0)
                    self.update_progress_text("OpenCL patches applied!")
                    self.log("\n✓ OpenCL GPU acceleration patches applied successfully!", "success")
                    self.log(
                        "OpenCL filters (blur, sharpen, denoise, etc.) should now use your GPU.",
                        "info",
                    )

                    QTimer.singleShot(
                        0,
                        lambda: QMessageBox.information(
                            self,
                            "OpenCL Patches Applied",
                            "OpenCL GPU acceleration patches have been applied successfully!\n\n"
                            "GPU-accelerated filters should now work correctly.\n"
                            "The libraster.dll patch will need to be re-applied after Affinity updates.",
                        ),
                    )

                except Exception as e:
                    self.log(f"Error applying OpenCL patches: {e}", "error")
                    import traceback
                    self.log(traceback.format_exc(), "error")
                finally:
                    self.end_operation()

            threading.Thread(target=apply_opencl_thread, daemon=True).start()

        except Exception as e:
            self.log(f"Error: {e}", "error")

    # =========================================================================
    # Canva OAuth Login Patches
    # =========================================================================

    def ensure_ssa_fix_files(self, silent=False):
        """Ensure SharedStorageAccessManagerFix patcher files are available"""
        try:
            dest_dir = Path(self.directory) / "Patch" / "SharedStorageAccessManagerFix"
            dest_dir.mkdir(parents=True, exist_ok=True)

            files_to_get = {
                "SharedStorageAccessManagerFix.cs": "https://raw.githubusercontent.com/ryzendew/Linux-Affinity-Installer/main/Patch/SharedStorageAccessManagerFix/SharedStorageAccessManagerFix.cs",
                "SharedStorageAccessManagerFix.csproj": "https://raw.githubusercontent.com/ryzendew/Linux-Affinity-Installer/main/Patch/SharedStorageAccessManagerFix/SharedStorageAccessManagerFix.csproj",
                "AffinitySendURL.cs": "https://raw.githubusercontent.com/ryzendew/Linux-Affinity-Installer/main/Patch/SharedStorageAccessManagerFix/AffinitySendURL.cs",
            }

            script_dir = Path(__file__).parent
            source_dir = script_dir.parent / "Patch" / "SharedStorageAccessManagerFix"

            for filename, github_url in files_to_get.items():
                dest_file = dest_dir / filename
                if dest_file.exists() and dest_file.stat().st_size > 0:
                    continue

                source_file = source_dir / filename
                if source_file.exists():
                    try:
                        shutil.copy2(source_file, dest_file)
                        if not silent:
                            self.log(f"Copied {filename} to Patch/SharedStorageAccessManagerFix/", "info")
                        continue
                    except Exception:
                        pass

                if not dest_file.exists():
                    if not silent:
                        self.log(f"Downloading {filename} from GitHub...", "info")
                    try:
                        if self.download_file(github_url, str(dest_file), filename):
                            if not silent:
                                self.log(f"Downloaded {filename}", "success")
                        else:
                            if not silent:
                                self.log(f"Failed to download {filename}", "error")
                            return False
                    except Exception as e:
                        if not silent:
                            self.log(f"Error downloading {filename}: {e}", "error")
                        return False

            return True
        except Exception as e:
            if not silent:
                self.log(f"Error ensuring SSA fix files: {e}", "error")
            return False

    def build_ssa_fix(self):
        """Build the SharedStorageAccessManagerFix .NET project"""
        patch_dir = Path(self.directory) / "Patch" / "SharedStorageAccessManagerFix"
        csproj = patch_dir / "SharedStorageAccessManagerFix.csproj"

        if not csproj.exists():
            self.log(f"SharedStorageAccessManagerFix.csproj not found: {csproj}", "error")
            return None

        self.log(f"Building SharedStorageAccessManagerFix from: {patch_dir}", "info")

        output_dir = patch_dir / "bin" / "Release"
        success, stdout, stderr = self.run_command(
            [
                "dotnet",
                "build",
                str(csproj.resolve()),
                "-c",
                "Release",
                "-o",
                str(output_dir.resolve()),
                "--no-incremental",
                "-p:BuildProjectReferences=false",
                "/p:DisableImplicitNuGetFallbackFolder=true",
            ],
            check=False,
            capture=True,
        )

        if not success:
            self.log(f"Failed to build SharedStorageAccessManagerFix: {stderr}", "error")
            return None

        for name in ["SharedStorageAccessManagerFix", "SharedStorageAccessManagerFix.dll"]:
            candidate = output_dir / name
            if candidate.exists():
                self.log("SharedStorageAccessManagerFix built successfully", "success")
                return candidate

        self.log("Built SSA fix not found at expected location", "error")
        return None

    def run_ssa_fix(self, dll_path=None):
        """Run the SharedStorageAccessManagerFix on Serif.Affinity.dll"""
        if dll_path is None:
            dll_path = str(
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / "Affinity"
                / "Serif.Affinity.dll"
            )

        if not Path(dll_path).exists():
            self.log(f"Serif.Affinity.dll not found: {dll_path}", "warning")
            return False

        patcher_exe = self.build_ssa_fix()
        if not patcher_exe:
            self.log("Failed to build SharedStorageAccessManagerFix", "error")
            return False

        self.log(f"Running SharedStorageAccessManagerFix on: {dll_path}", "info")

        if patcher_exe.suffix == ".dll":
            cmd = ["dotnet", str(patcher_exe), dll_path]
        else:
            cmd = [str(patcher_exe), dll_path]

        success, stdout, stderr = self.run_command(cmd, check=False, capture=True)

        if stdout:
            for line in stdout.strip().split("\n"):
                if line.strip():
                    self.log(line.strip(), "success" if "patched" in line.lower() or "already" in line.lower() else "info")

        if success:
            self.log("SharedStorageAccessManager fix applied", "success")
            return True
        else:
            self.log(f"SharedStorageAccessManager fix failed: {stderr}", "error")
            return False

    def setup_tls_relay(self):
        """Run the TLS relay one-time setup (hosts entry, socat capability, cert)"""
        script_dir = Path(__file__).parent
        relay_script = script_dir / "AffinityTLSRelay.sh"

        if not relay_script.exists():
            self.log("AffinityTLSRelay.sh not found", "error")
            return False

        # Check dependencies
        if not self.check_command("socat"):
            self.log("socat is not installed. Installing...", "info")
            install_cmd = None
            if self.distro in ["arch", "cachyos", "endeavouros", "xerolinux"]:
                install_cmd = ["sudo", "pacman", "-S", "--needed", "--noconfirm", "socat", "bind-tools"]
            elif self.distro in ["fedora", "nobara"]:
                install_cmd = ["sudo", "dnf", "install", "-y", "socat", "bind-utils"]
            elif self.distro in ["pikaos", "pop", "debian"]:
                install_cmd = ["sudo", "apt", "install", "-y", "socat", "dnsutils"]

            if install_cmd:
                success, _, stderr = self.run_command(install_cmd, check=False, capture=True)
                if not success:
                    self.log(f"Failed to install socat: {stderr}", "error")
                    return False
                self.log("socat installed", "success")

        self.log("[INFO] TLS Relay One-Time Setup", "info")

        # --- /etc/hosts entry ---
        hosts_ok = False
        try:
            with open("/etc/hosts", "r") as f:
                if any("affinity.api.serifservices.com" in line and line.strip().startswith("127.0.0.1")
                       for line in f):
                    self.log("[✓] /etc/hosts entry already present", "success")
                    hosts_ok = True
        except OSError:
            pass

        if not hosts_ok:
            self.log("[INFO] Adding /etc/hosts entry (requires authentication)...", "info")
            # Use pkexec for graphical auth prompt, fall back to sudo
            priv_cmd = "pkexec" if self.check_command("pkexec") else "sudo"
            success, _, stderr = self.run_command(
                ["bash", "-c", f'echo "127.0.0.1 affinity.api.serifservices.com" | {priv_cmd} tee -a /etc/hosts >/dev/null'],
                check=False, capture=True,
            )
            if success:
                self.log("[✓] /etc/hosts entry added", "success")
                hosts_ok = True
            else:
                self.log("[ERROR] Failed to add /etc/hosts entry", "error")

        # --- socat port-binding capability ---
        socat_ok = False
        socat_path = shutil.which("socat")
        if socat_path:
            # Resolve symlinks — setcap can't operate on symlinks
            socat_path = str(Path(socat_path).resolve())
            cap_check, cap_out, _ = self.run_command(
                ["getcap", socat_path], check=False, capture=True,
            )
            if cap_out and "cap_net_bind_service" in cap_out:
                self.log("[✓] socat already has port-binding capability", "success")
                socat_ok = True
            else:
                self.log("[INFO] Granting socat port-binding capability (requires authentication)...", "info")
                priv_cmd = "pkexec" if self.check_command("pkexec") else "sudo"
                success, _, stderr = self.run_command(
                    [priv_cmd, "setcap", "cap_net_bind_service=+ep", socat_path],
                    check=False, capture=True,
                )
                if success:
                    self.log("[✓] socat capability granted", "success")
                    socat_ok = True
                else:
                    self.log("[ERROR] Failed to set socat capability", "error")

        # --- Generate TLS certificate ---
        relay_dir = Path(self.directory) / "tls-relay"
        server_pem = relay_dir / "server.pem"
        if server_pem.exists():
            self.log("[✓] TLS certificate already exists", "success")
        else:
            self.log("[INFO] Generating self-signed certificate...", "info")
            relay_dir.mkdir(parents=True, exist_ok=True)
            success, _, stderr = self.run_command(
                ["bash", "-c",
                 f'(umask 077 && openssl req -x509 -newkey rsa:2048 '
                 f'-keyout "{relay_dir}/key.pem" -out "{relay_dir}/cert.pem" '
                 f'-days 3650 -nodes -subj "/CN=affinity.api.serifservices.com" 2>/dev/null) && '
                 f'cat "{relay_dir}/cert.pem" "{relay_dir}/key.pem" > "{server_pem}" && '
                 f'chmod 600 "{server_pem}" && '
                 f'rm -f "{relay_dir}/key.pem" "{relay_dir}/cert.pem"'],
                check=False, capture=True,
            )
            if success:
                self.log("[✓] Certificate generated", "success")
            else:
                self.log(f"[ERROR] Certificate generation failed: {stderr}", "error")

        if not hosts_ok or not socat_ok:
            self.log("⚠ TLS relay setup failed (Canva login may not work)", "warning")
            return False

        self.log("[✓] TLS relay setup complete", "success")
        return True

    def start_tls_relay(self):
        """Start the TLS relay (called before launching Affinity)"""
        script_dir = Path(__file__).parent
        relay_script = script_dir / "AffinityTLSRelay.sh"

        if not relay_script.exists():
            return False

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        success, _, _ = self.run_command(
            ["bash", str(relay_script), "start"],
            check=False,
            capture=True,
            env=env,
        )
        return success

    def setup_canva_login(self):
        """Set up everything needed for Canva OAuth login (UI button handler)"""
        try:
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Enable Canva Login", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Check Wine
            wine = self.get_wine_path("wine")
            if not wine.exists():
                self.show_message(
                    "Wine Not Found",
                    "Wine must be installed before enabling Canva login.\n\n"
                    "Please run 'One-Click Setup' or 'Setup Wine Environment' first.",
                    "warning",
                )
                return

            # Check .NET SDK
            if not self.check_dotnet_sdk():
                self.log(".NET SDK not found. Attempting to install...", "info")
                if not self.install_dotnet_sdk():
                    self.log("Failed to install .NET SDK", "error")
                    self.show_message(
                        ".NET SDK Required",
                        ".NET SDK 8.0+ is required for the Canva login patch.\n\n"
                        "Please install it manually, then try again.",
                        "warning",
                    )
                    return

            self.start_operation("Enable Canva Login")

            def canva_login_thread():
                try:
                    self.update_progress(0.0)
                    self.update_progress_text("Downloading patch files...")

                    # Step 1: Ensure patch files
                    if not self.ensure_ssa_fix_files():
                        self.log("Failed to obtain patch files", "error")
                        self.end_operation()
                        return
                    self.update_progress(0.2)

                    # Step 2: Build and run SharedStorageAccessManagerFix
                    self.update_progress_text("Patching Serif.Affinity.dll...")
                    if not self.run_ssa_fix():
                        self.log("SharedStorageAccessManager fix failed", "error")
                        self.end_operation()
                        return
                    self.update_progress(0.5)

                    # Step 3: Set up TLS relay
                    self.update_progress_text("Setting up TLS relay...")
                    if not self.setup_tls_relay():
                        self.log("TLS relay setup failed (Canva login may not work)", "warning")
                    self.update_progress(0.8)

                    # Step 4: Install AffinitySendURL.exe
                    self.update_progress_text("Installing OAuth callback tool...")
                    script_dir = Path(__file__).parent
                    sendurl_src = script_dir / "AffinitySendURL.exe"
                    tools_dir = Path(self.directory) / "tools"
                    sendurl_dest = tools_dir / "AffinitySendURL.exe"
                    if sendurl_src.exists():
                        tools_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(sendurl_src), str(sendurl_dest))
                        self.log(f"[✓] AffinitySendURL.exe installed to {sendurl_dest}", "success")
                    elif sendurl_dest.exists():
                        self.log("[✓] AffinitySendURL.exe already installed", "success")
                    else:
                        self.log("AffinitySendURL.exe not found — OAuth callback will not work", "warning")
                        self.log("Compile from Patch/SharedStorageAccessManagerFix/AffinitySendURL.cs", "info")
                    self.update_progress(0.85)

                    # Step 5: Install URL handler and register mime type
                    self.update_progress_text("Registering URL handler...")
                    url_handler_script = script_dir / "AffinityURLHandler.sh"
                    desktop_template = script_dir / "affinity-url-handler.desktop"
                    desktop_dest = Path.home() / ".local" / "share" / "applications" / "affinity-url-handler.desktop"

                    if url_handler_script.exists():
                        # Make the URL handler script executable
                        url_handler_script.chmod(0o755)

                        if desktop_template.exists():
                            # Read template and replace placeholder with actual path
                            desktop_content = desktop_template.read_text()
                            desktop_content = desktop_content.replace(
                                "PLACEHOLDER_SCRIPT_PATH", str(url_handler_script)
                            )
                            # Ensure destination directory exists
                            desktop_dest.parent.mkdir(parents=True, exist_ok=True)
                            desktop_dest.write_text(desktop_content)
                            self.log(f"[✓] URL handler desktop file installed", "success")
                        else:
                            # Create desktop file directly if template is missing
                            desktop_dest.parent.mkdir(parents=True, exist_ok=True)
                            desktop_dest.write_text(
                                "[Desktop Entry]\n"
                                "Type=Application\n"
                                "Name=Affinity URL Handler\n"
                                "Comment=Handles affinity:// OAuth callback URLs for Canva sign-in\n"
                                f"Exec={url_handler_script} %u\n"
                                "MimeType=x-scheme-handler/affinity;\n"
                                "NoDisplay=true\n"
                            )
                            self.log(f"[✓] URL handler desktop file created", "success")

                        # Register as affinity:// protocol handler
                        self.run_command(
                            ["xdg-mime", "default", "affinity-url-handler.desktop",
                             "x-scheme-handler/affinity"],
                            check=False, capture=True,
                        )
                        self.log("[✓] Registered as affinity:// protocol handler", "success")
                    else:
                        self.log("AffinityURLHandler.sh not found — URL handler not registered", "warning")
                        self.log("See docs/CANVA-OAUTH-LOGIN.md for manual setup.", "info")

                    self.update_progress(1.0)
                    self.update_progress_text("Canva login setup complete!")
                    self.log("\n✓ Canva login patches applied!", "success")

                    QTimer.singleShot(
                        0,
                        lambda: QMessageBox.information(
                            self,
                            "Canva Login Enabled",
                            "Canva login has been fully configured!\n\n"
                            "• IL patch applied to Serif.Affinity.dll\n"
                            "• TLS relay configured (starts with Affinity)\n"
                            "• OAuth URL handler registered\n\n"
                            "The IL patch will need to be re-applied after Affinity updates.",
                        ),
                    )

                except Exception as e:
                    self.log(f"Error setting up Canva login: {e}", "error")
                    import traceback
                    self.log(traceback.format_exc(), "error")
                finally:
                    self.end_operation()

            threading.Thread(target=canva_login_thread, daemon=True).start()

        except Exception as e:
            self.log(f"Error: {e}", "error")

    def launch_affinity_v3(self):
        """Launch Affinity v3 with optimized environment variables"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Launch Affinity v3", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Affinity is installed
        affinity_exe = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / "Affinity"
            / "Affinity.exe"
        )
        if not affinity_exe.exists():
            self.log("✗ Affinity v3 is not installed", "error")
            self.log(
                "Please install Affinity v3 first using 'Update Affinity Applications' → 'Affinity (Unified)'",
                "info",
            )
            self.show_message(
                "Affinity Not Found",
                "Affinity v3 is not installed.\n\nPlease install it first using:\n'Update Affinity Applications' → 'Affinity (Unified)'",
                "warning",
            )
            return

        # Check if Wine is set up
        wine_bin = self.get_wine_path("wine")
        if not wine_bin.exists():
            self.log("✗ Wine is not set up", "error")
            self.log("Please run 'Setup Wine Environment' first", "info")
            self.show_message(
                "Wine Not Found",
                "Wine is not set up.\n\nPlease run 'Setup Wine Environment' first.",
                "warning",
            )
            return

        self.log("Setting up environment variables...", "info")

        # Prepare environment variables
        env = os.environ.copy()

        # Set PATH to include Wine binaries (only for custom Wine builds)
        wine_dir = self.get_wine_dir()
        if wine_dir:
            wine_dir_str = str(wine_dir)
            current_path = env.get("PATH", "")
            env["PATH"] = f"{wine_dir_str}/bin:{current_path}"
        # For system Wine, it's already in PATH

        # Set Wine-related environment variables
        env["WINE"] = str(wine_bin)
        env["WINEPREFIX"] = self.directory
        env["WINEDEBUG"] = "-all,fixme-all"
        # Check if patched opencl.dll is installed; if not, keep OpenCL disabled
        # to avoid Wine's broken stubs causing "Unsupported Graphics Card" errors
        orig_opencl = wine_dir / "lib" / "wine" / "x86_64-windows" / "opencl.dll.orig" if wine_dir else None
        if orig_opencl and orig_opencl.exists():
            # Patched opencl.dll is installed (backup exists from patching)
            env["WINEDLLOVERRIDES"] = "d3d9=b"
            env["PersonaIsOpenCLCPUBackendEnabled"] = "1"
            if self.has_amd_gpu():
                env["GPU_DEVICE_ORDINAL"] = "0"
        else:
            # No OpenCL patch — keep upstream behavior (OpenCL disabled)
            env["WINEDLLOVERRIDES"] = "opencl=;d3d9=b"

        # Add GPU selection environment variables if configured
        gpu_env = self.get_gpu_env_vars()
        if gpu_env:
            # Parse GPU env vars and add to environment
            for env_var in gpu_env.strip().split():
                if "=" in env_var:
                    key, value = env_var.split("=", 1)
                    env[key] = value

        # Check renderer setting - only set DXVK/VKD3D if Vulkan is selected
        renderer = self.get_renderer_setting()

        if renderer == "vulkan":
            # DXVK settings (only for Vulkan renderer)
            env["DXVK_ASYNC"] = "0"
            env["DXVK_CONFIG"] = (
                "d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1"
            )
            env["DXVK_FRAME_RATE"] = "60"
            env["DXVK_LOG_LEVEL"] = "none"

            # VKD3D settings (only for Vulkan renderer)
            env["VKD3D_DEBUG"] = "none"
            env["VKD3D_DISABLE_EXTENSIONS"] = "VK_KHR_present_id"
            env["VKD3D_FEATURE_LEVEL"] = "12_1"
            env["VKD3D_FRAME_RATE"] = "60"
            env["VKD3D_SHADER_DEBUG"] = "none"
            env["VKD3D_SHADER_MODEL"] = "6_5"
        else:
            # For OpenGL or GDI, disable DXVK/VKD3D to prevent Vulkan initialization errors
            # Also disable DLL overrides that might force Vulkan
            env["DXVK_STATE_CACHE"] = "0"
            env["DXVK_HUD"] = "0"
            # Don't set VKD3D variables for OpenGL/GDI
            self.log(
                f"Renderer is set to {renderer.upper()}, DXVK/VKD3D disabled", "info"
            )

            # If OpenGL/GDI is selected and OpenCL is disabled, remove d3d12 DLL overrides
            # that might force Vulkan usage
            if not self.is_opencl_enabled():
                self.log(
                    "Removing d3d12 DLL overrides to prevent Vulkan initialization",
                    "info",
                )
                try:
                    wine = self.get_wine_path("wine")
                    reg_env = os.environ.copy()
                    reg_env["WINEPREFIX"] = self.directory
                    # Remove d3d12 and d3d12core overrides
                    self.run_command(
                        [
                            str(wine),
                            "reg",
                            "delete",
                            "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                            "/v",
                            "d3d12",
                            "/f",
                        ],
                        check=False,
                        env=reg_env,
                        capture=True,
                    )
                    self.run_command(
                        [
                            str(wine),
                            "reg",
                            "delete",
                            "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                            "/v",
                            "d3d12core",
                            "/f",
                        ],
                        check=False,
                        env=reg_env,
                        capture=True,
                    )
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove d3d12 DLL overrides: {e}", "warning"
                    )

        self.log("✓ Environment variables configured", "success")
        self.log(f"Wine: {wine_bin}", "info")
        self.log(f"WINEPREFIX: {self.directory}", "info")
        self.log(f"Affinity: {affinity_exe}", "info")

        # Launch in background thread to avoid freezing UI
        def _launch_thread():
            try:
                # Start TLS relay for Canva login (lightweight, no build step)
                self.start_tls_relay()

                # Launch Affinity using wine start
                self.log("\nLaunching Affinity v3...", "info")
                wine_start_cmd = [
                    str(wine_bin),
                    "start",
                    "C:/Program Files/Affinity/Affinity/Affinity.exe",
                ]

                process = subprocess.Popen(
                    wine_start_cmd,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

                self.log("✓ Affinity v3 launched successfully", "success")
                self.log("The application should open in a moment...", "info")

            except Exception as e:
                self.log(f"✗ Failed to launch Affinity v3: {e}", "error")
                self.show_message(
                    "Launch Failed",
                    f"Failed to launch Affinity v3:\n\n{str(e)}",
                    "error",
                )

        threading.Thread(target=_launch_thread, daemon=True).start()

    def download_affinity_installer(self):
        """Download the Affinity installer by itself"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Download Affinity Installer", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Ask user where to save the file
        downloads_dir = Path.home() / "Downloads"
        default_path = downloads_dir / "Affinity-x64.exe"

        # Suggest Downloads folder by default, but let user choose
        suggested_path = str(default_path)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Affinity Installer",
            suggested_path,
            "Executable files (*.exe);;All files (*.*)",
        )

        if not save_path:
            self.log("Download cancelled.", "warning")
            return

        save_path_obj = Path(save_path)

        # Start operation and thread to download
        self.start_operation("Download Affinity Installer")
        threading.Thread(
            target=self._download_affinity_installer_thread,
            args=(save_path_obj,),
            daemon=True,
        ).start()

        # The rest of the logic should be in the _download_affinity_installer_thread method
        # This is just a placeholder to fix the syntax error
        pass

    def install_affinity_plugin_loader(self):
        """Download and install the latest AffinityPluginLoader + WineFix into the Affinity install dir,
        then update Affinity.desktop to launch via AffinityHook.exe."""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Install AffinityPluginLoader + WineFix", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        if not install_dir.exists():
            self.log("✗ Affinity install directory not found:", "error")
            self.log(f"  {install_dir}", "error")
            self.log("Please install Affinity first.", "info")
            self.show_message(
                "Affinity Not Found",
                f"Affinity install directory not found:\n{install_dir}\n\nPlease install Affinity first.",
                QMessageBox.Icon.Warning,
            )
            return

        self.start_operation("Install AffinityPluginLoader")
        threading.Thread(
            target=self._install_affinity_plugin_loader_thread,
            args=(install_dir,),
            daemon=True,
        ).start()

    def _install_affinity_plugin_loader_thread(self, install_dir):
        """Worker thread: fetch latest release assets, download both zips, extract, patch desktop."""
        try:
            # ── 1. Query GitHub API for latest release ──────────────────────────────
            self.log("Fetching latest release info from GitHub...", "info")
            api_url = "https://api.github.com/repos/noahc3/AffinityPluginLoader/releases/latest"
            request = urllib.request.Request(api_url)
            request.add_header("User-Agent", "AffinityLinuxInstaller")
            try:
                with urllib.request.urlopen(request, timeout=15) as resp:
                    release_data = json.loads(resp.read().decode())
            except Exception as e:
                self.log(f"✗ Failed to fetch release info: {e}", "error")
                self.finish_operation(False)
                return

            tag = release_data.get("tag_name", "unknown")
            assets = release_data.get("assets", [])
            self.log(f"Latest release: {tag}", "info")
            self.log(f"Found {len(assets)} asset(s) in release", "info")

            # ── 2. Locate the two zip assets by prefix ──────────────────────────────
            apl_asset = None
            winefix_asset = None
            for asset in assets:
                name = asset.get("name", "")
                if name.startswith("affinitypluginloader-") and name.endswith(".zip"):
                    apl_asset = asset
                elif name.startswith("apl-winefix-") and name.endswith(".zip"):
                    winefix_asset = asset

            if not apl_asset:
                self.log(
                    "✗ Could not find affinitypluginloader-*.zip in release assets",
                    "error",
                )
                self.log("Available assets:", "info")
                for asset in assets:
                    self.log(f"  • {asset.get('name', '?')}", "info")
                self.finish_operation(False)
                return
            if not winefix_asset:
                self.log(
                    "✗ Could not find apl-winefix-*.zip in release assets", "error"
                )
                self.log("Available assets:", "info")
                for asset in assets:
                    self.log(f"  • {asset.get('name', '?')}", "info")
                self.finish_operation(False)
                return

            self.log(f"AffinityPluginLoader asset: {apl_asset['name']}", "info")
            self.log(f"WineFix asset:              {winefix_asset['name']}", "info")

            # ── 3. Download both zips to a temp directory ───────────────────────────
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                apl_zip_path = tmpdir_path / apl_asset["name"]
                winefix_zip_path = tmpdir_path / winefix_asset["name"]

                for asset, dest in [
                    (apl_asset, apl_zip_path),
                    (winefix_asset, winefix_zip_path),
                ]:
                    url = asset["browser_download_url"]
                    name = asset["name"]
                    size = asset.get("size", 0)
                    self.log(f"Downloading {name} ({size // 1024} KB)...", "info")
                    self.progress_signal.emit(0)
                    try:

                        def _progress(block_num, block_size, total_size):
                            if total_size > 0:
                                pct = min(
                                    100.0, block_num * block_size / total_size * 100
                                )
                                self.progress_signal.emit(pct)

                        urllib.request.urlretrieve(url, str(dest), reporthook=_progress)
                        self.progress_signal.emit(100)
                        self.log(f"  ✓ Downloaded {name}", "success")
                    except Exception as e:
                        self.log(f"✗ Failed to download {name}: {e}", "error")
                        self.finish_operation(False)
                        return

                # ── 4. Extract AffinityPluginLoader zip ─────────────────────────────
                self.log(f"\nExtracting {apl_asset['name']} → {install_dir}", "info")
                if not self._extract_zip_verified(apl_zip_path, install_dir):
                    self.finish_operation(False)
                    return

                # ── 5. Extract WineFix zip ───────────────────────────────────────────
                # The winefix zip contains an apl/ subdirectory with d2d1.dll (and
                # potentially other files). We extract the zip to a staging area first
                # so we can verify the layout, then copy everything into install_dir.
                self.log(f"\nExtracting {winefix_asset['name']}...", "info")
                winefix_stage = tmpdir_path / "winefix_stage"
                winefix_stage.mkdir()
                if not self._extract_zip_verified(winefix_zip_path, winefix_stage):
                    self.finish_operation(False)
                    return

                # Copy all extracted files/folders into the Affinity install dir
                self.log(f"Installing WineFix files → {install_dir}", "info")
                try:
                    self._copy_tree_verified(winefix_stage, install_dir)
                except Exception as e:
                    self.log(f"✗ Failed to install WineFix files: {e}", "error")
                    self.finish_operation(False)
                    return

                # Verify d2d1.dll landed in the apl/ subfolder
                d2d1_path = install_dir / "apl" / "d2d1.dll"
                if d2d1_path.exists():
                    self.log(f"  ✓ apl/d2d1.dll verified", "success")
                else:
                    self.log(
                        "  ⚠ apl/d2d1.dll not found after extraction — check zip layout",
                        "warning",
                    )

            # ── 6. Verify AffinityHook.exe is present ───────────────────────────────
            hook_exe = install_dir / "AffinityHook.exe"
            if hook_exe.exists():
                self.log(f"\n✓ AffinityHook.exe present at {hook_exe}", "success")
            else:
                self.log(
                    f"\n⚠ AffinityHook.exe not found at {hook_exe} — desktop entry will still be updated",
                    "warning",
                )

            # ── 7. Patch Affinity.desktop to use AffinityHook.exe ──────────────────
            self._patch_affinity_desktop_for_hook()

            self.log(
                "\n✓ AffinityPluginLoader + WineFix installation complete!", "success"
            )
            self.log(
                "Affinity will now launch via AffinityHook.exe from the desktop shortcut.",
                "info",
            )
            self.finish_operation(True)
            self.show_message(
                "Installation Complete",
                f"AffinityPluginLoader ({tag}) and WineFix have been installed successfully.\n\n"
                "Affinity.desktop has been updated to launch via AffinityHook.exe.",
                QMessageBox.Icon.Information,
            )

        except Exception as e:
            self.log(f"✗ Unexpected error during installation: {e}", "error")
            self.finish_operation(False)

    def _extract_zip_verified(self, zip_path, dest_dir):
        """Extract a zip file into dest_dir, verifying every member extracts successfully.

        Returns True on success, False (with error logged) on failure.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                members = zf.namelist()
                self.log(f"  Archive contains {len(members)} file(s)", "info")
                failed = []
                for member in members:
                    try:
                        zf.extract(member, str(dest_dir))
                    except Exception as ex:
                        failed.append((member, str(ex)))

                if failed:
                    self.log(f"  ✗ {len(failed)} file(s) failed to extract:", "error")
                    for name, err in failed:
                        self.log(f"    • {name}: {err}", "error")
                    return False

                # Post-extraction verification: every file that isn't a dir must exist
                verify_errors = []
                for member in members:
                    if member.endswith("/"):
                        continue  # directory entry
                    target = dest_dir / member
                    if not target.exists():
                        verify_errors.append(member)

                if verify_errors:
                    self.log(
                        f"  ✗ {len(verify_errors)} file(s) missing after extraction:",
                        "error",
                    )
                    for name in verify_errors:
                        self.log(f"    • {name}", "error")
                    return False

                self.log(
                    f"  ✓ All {len(members)} entries extracted and verified", "success"
                )
                return True

        except zipfile.BadZipFile as e:
            self.log(f"  ✗ Bad zip file {zip_path.name}: {e}", "error")
            return False
        except Exception as e:
            self.log(f"  ✗ Extraction error for {zip_path.name}: {e}", "error")
            return False

    def _copy_tree_verified(self, src_dir, dst_dir):
        """Recursively copy src_dir contents into dst_dir, logging each file."""
        src_dir = Path(src_dir)
        dst_dir = Path(dst_dir)
        copied = 0
        for src_file in src_dir.rglob("*"):
            if src_file.is_dir():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_file), str(dst_file))
            self.log(f"  ✓ {rel}", "success")
            copied += 1
        self.log(f"  Copied {copied} file(s) total", "info")

    def _patch_affinity_desktop_for_hook(self):
        """Edit ~/.local/share/applications/Affinity.desktop to replace Affinity.exe
        with AffinityHook.exe on the Exec= line."""
        desktop_file = (
            Path.home() / ".local" / "share" / "applications" / "Affinity.desktop"
        )

        if not desktop_file.exists():
            self.log(
                f"⚠ Affinity.desktop not found at {desktop_file} — skipping desktop patch",
                "warning",
            )
            self.log(
                "  You will need to manually update your launcher to use AffinityHook.exe",
                "info",
            )
            return

        self.log(f"\nPatching {desktop_file}...", "info")
        try:
            with open(desktop_file, "r") as f:
                lines = f.readlines()

            new_lines = []
            patched = False
            for line in lines:
                if (
                    line.startswith("Exec=")
                    and "Affinity.exe" in line
                    and "AffinityHook.exe" not in line
                ):
                    original = line.rstrip()
                    # Replace only the bare "Affinity.exe" token — avoid touching e.g. "AffinityPhoto.exe"
                    new_line = re.sub(
                        r"(?<![A-Za-z])Affinity\.exe", "AffinityHook.exe", line
                    )
                    new_lines.append(new_line)
                    patched = True
                    self.log(f"  Before: {original}", "info")
                    self.log(f"  After:  {new_line.rstrip()}", "success")
                else:
                    new_lines.append(line)

            if patched:
                with open(desktop_file, "w") as f:
                    f.writelines(new_lines)
                self.log(
                    "✓ Affinity.desktop updated to use AffinityHook.exe", "success"
                )
            else:
                self.log(
                    "⚠ Exec= line already uses AffinityHook.exe or no matching line found — no change made",
                    "warning",
                )

        except Exception as e:
            self.log(f"✗ Failed to patch Affinity.desktop: {e}", "error")

    def install_affinity_plugin_loader(self):
        """Download and install the latest AffinityPluginLoader + WineFix from GitHub"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Install AffinityPluginLoader + WineFix", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        if not install_dir.exists():
            self.log("✗ Affinity installation directory not found:", "error")
            self.log(f"  {install_dir}", "error")
            self.log("Please install Affinity first.", "info")
            self.show_message(
                "Affinity Not Installed",
                f"Could not find:\n{install_dir}\n\nPlease install Affinity first.",
                QMessageBox.Icon.Warning,
            )
            return

        self.start_operation("Install AffinityPluginLoader")
        threading.Thread(
            target=self._install_affinity_plugin_loader_thread, daemon=True
        ).start()

    def _install_affinity_plugin_loader_thread(self, standalone=True):
        """Worker thread: fetch latest release, download both zips, extract, patch desktop file"""
        try:
            install_dir = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / "Affinity"
            )

            # ── 1. Fetch latest release metadata from GitHub ──────────────────────────
            self.log("Fetching latest release info from GitHub...", "info")
            api_url = "https://api.github.com/repos/noahc3/AffinityPluginLoader/releases/latest"
            request = urllib.request.Request(api_url)
            request.add_header("User-Agent", "AffinityLinuxInstaller")

            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    release_data = json.loads(response.read().decode())
            except Exception as e:
                self.log(f"✗ Failed to fetch release info: {e}", "error")
                if standalone:
                    self.end_operation()
                return

            tag = release_data.get("tag_name", "unknown")
            assets = release_data.get("assets", [])
            self.log(f"Latest release: {tag}", "info")

            if not assets:
                self.log("✗ No assets found in latest release.", "error")
                if standalone:
                    self.end_operation()
                return

            # ── 2. Locate the two zip assets by prefix ────────────────────────────────
            apl_asset = next(
                (
                    a
                    for a in assets
                    if a["name"].lower().startswith("affinitypluginloader")
                    and a["name"].endswith(".zip")
                ),
                None,
            )
            winefix_asset = next(
                (
                    a
                    for a in assets
                    if a["name"].lower().startswith("winefix")
                    and a["name"].endswith(".zip")
                ),
                None,
            )

            if not apl_asset:
                self.log(
                    "✗ Could not find affinitypluginloader zip in release assets.",
                    "error",
                )
                self.log("Assets found:", "info")
                for a in assets:
                    self.log(f"  - {a['name']}", "info")
                if standalone:
                    self.end_operation()
                return

            if not winefix_asset:
                self.log("✗ Could not find apl-winefix zip in release assets.", "error")
                self.log("Assets found:", "info")
                for a in assets:
                    self.log(f"  - {a['name']}", "info")
                if standalone:
                    self.end_operation()
                return

            self.log(f"Found: {apl_asset['name']}", "success")
            self.log(f"Found: {winefix_asset['name']}", "success")

            # ── 3. Download and extract each zip into a temp directory ─────────────────
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)

                for asset, label in [
                    (apl_asset, "AffinityPluginLoader"),
                    (winefix_asset, "WineFix"),
                ]:
                    url = asset["browser_download_url"]
                    dest_zip = tmp_path / asset["name"]
                    self.log(f"Downloading {label} ({asset['name']})...", "info")
                    self.update_progress(0)

                    try:

                        def _progress(block_num, block_size, total_size):
                            if total_size > 0:
                                pct = min(
                                    100.0, block_num * block_size / total_size * 100
                                )
                                self.update_progress(pct)

                        urllib.request.urlretrieve(
                            url, str(dest_zip), reporthook=_progress
                        )
                        self.update_progress(100)
                        self.log(f"✓ Downloaded {asset['name']}", "success")
                    except Exception as e:
                        self.log(f"✗ Failed to download {asset['name']}: {e}", "error")
                        if standalone:
                            self.end_operation()
                        return

                    # Verify it is a valid zip
                    if not zipfile.is_zipfile(str(dest_zip)):
                        self.log(
                            f"✗ Downloaded file is not a valid zip: {asset['name']}",
                            "error",
                        )
                        if standalone:
                            self.end_operation()
                        return

                    extract_dir = tmp_path / f"extracted_{label}"
                    extract_dir.mkdir()

                    self.log(f"Extracting {label}...", "info")
                    try:
                        with zipfile.ZipFile(str(dest_zip), "r") as zf:
                            members = zf.namelist()
                            self.log(f"  Contents: {', '.join(members)}", "info")
                            zf.extractall(str(extract_dir))
                        self.log(f"✓ Extracted {label}", "success")
                    except Exception as e:
                        self.log(f"✗ Failed to extract {asset['name']}: {e}", "error")
                        if standalone:
                            self.end_operation()
                        return

                    # ── 4. Copy files into the Affinity install directory ──────────────
                    self.log(
                        f"Installing {label} files into Affinity directory...", "info"
                    )
                    installed_count = 0
                    try:
                        for item in extract_dir.rglob("*"):
                            if item.is_file():
                                # Preserve relative sub-directory structure (e.g. apl/d2d1.dll)
                                relative = item.relative_to(extract_dir)
                                dest_file = install_dir / relative
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(str(item), str(dest_file))
                                self.log(f"  Installed: {relative}", "info")
                                installed_count += 1
                    except Exception as e:
                        self.log(f"✗ Failed to copy {label} files: {e}", "error")
                        if standalone:
                            self.end_operation()
                        return

                    if installed_count == 0:
                        self.log(
                            f"⚠ No files were installed from {label} — archive may be empty or structured unexpectedly.",
                            "warning",
                        )
                    else:
                        self.log(
                            f"✓ {label}: {installed_count} file(s) installed", "success"
                        )

            # ── 5. Verify AffinityHook.exe is present after install ───────────────────
            hook_exe = install_dir / "AffinityHook.exe"
            if not hook_exe.exists():
                self.log(
                    "⚠ AffinityHook.exe not found after installation — desktop file will NOT be patched.",
                    "warning",
                )
                self.log(
                    "  The plugin files were installed but the launcher hook is missing.",
                    "warning",
                )
                if standalone:
                    self.end_operation()
                return

            self.log("✓ AffinityHook.exe confirmed present", "success")

            # ── 6. Inform user, then immediately run AffinityHook ────────────────────
            self.log(
                "\nInforming user about AffinityPluginLoader installation...", "info"
            )
            self.show_message(
                "AffinityPluginLoader Installed",
                "AffinityPluginLoader + WineFix have been installed!\n\n"
                "The installer will now run AffinityHook.exe once in the background "
                "to complete its initialisation.\n\n"
                "You do not need to do anything — this will take a few seconds.",
                "info",
            )
            self.log("Running AffinityHook.exe to complete initialisation...", "info")
            try:
                # Use the exact same wine + env as the .desktop entry does
                wine_bin = str(self.get_wine_path("wine"))
                hook_exe_path = str(
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / "Affinity"
                    / "AffinityHook.exe"
                )
                env = os.environ.copy()
                env["WINEPREFIX"] = self.directory
                env["WINEDEBUG"] = "-all,fixme-all"
                # Apply GPU and DXVK env vars exactly as the .desktop does
                gpu_env = self.get_gpu_env_vars()
                dxvk_env = self.get_dxvk_env_vars()
                if gpu_env:
                    for var in gpu_env.strip().split():
                        if "=" in var:
                            k, v = var.split("=", 1)
                            env[k] = v
                if dxvk_env:
                    for var in dxvk_env.strip().split():
                        if "=" in var:
                            k, v = var.split("=", 1)
                            env[k] = v
                self.log(f'Launching: {wine_bin} "{hook_exe_path}"', "info")
                proc = subprocess.Popen(
                    [wine_bin, hook_exe_path],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.log(
                    "AffinityHook.exe launched — waiting 15 seconds then closing...",
                    "info",
                )
                try:
                    proc.wait(timeout=15)
                    self.log(
                        "AffinityHook.exe exited on its own within 15 seconds.", "info"
                    )
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    wineserver_bin = str(self.get_wine_path("wineserver"))
                    subprocess.run(
                        [wineserver_bin, "-k"],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self.log("✓ AffinityHook.exe closed after 15 seconds.", "success")
            except Exception as e:
                self.log(f"⚠ Could not run AffinityHook.exe: {e}", "warning")
                self.log("  You may need to run it once manually.", "info")

            # ── 7. Patch Affinity.desktop to launch AffinityHook.exe ─────────────────
            self.log("\nPatching Affinity.desktop to use AffinityHook.exe...", "info")
            desktop_file = (
                Path.home() / ".local" / "share" / "applications" / "Affinity.desktop"
            )

            if not desktop_file.exists():
                self.log(f"⚠ Desktop file not found: {desktop_file}", "warning")
                self.log(
                    "  You may need to create a desktop entry manually pointing to AffinityHook.exe.",
                    "info",
                )
            else:
                try:
                    with open(desktop_file, "r") as f:
                        lines = f.readlines()

                    new_lines = []
                    patched = False
                    for line in lines:
                        if (
                            line.startswith("Exec=")
                            and "Affinity.exe" in line
                            and "AffinityHook.exe" not in line
                        ):
                            new_line = line.replace("Affinity.exe", "AffinityHook.exe")
                            new_lines.append(new_line)
                            patched = True
                            self.log(f"  Old Exec: {line.strip()}", "info")
                            self.log(f"  New Exec: {new_line.strip()}", "info")
                        else:
                            new_lines.append(line)

                    if patched:
                        with open(desktop_file, "w") as f:
                            f.writelines(new_lines)
                        self.log(
                            "✓ Affinity.desktop updated to launch via AffinityHook.exe",
                            "success",
                        )
                    else:
                        self.log(
                            "⚠ Exec line already references AffinityHook.exe or Affinity.exe not found in Exec line — no change made.",
                            "warning",
                        )

                except Exception as e:
                    self.log(f"✗ Failed to patch desktop file: {e}", "error")

            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "info",
            )
            self.log("AffinityPluginLoader + WineFix installation complete!", "success")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                "info",
            )
            if standalone:
                self.end_operation()

        except Exception as e:
            self.log(
                f"✗ Unexpected error during AffinityPluginLoader installation: {e}",
                "error",
            )
            if standalone:
                self.end_operation()

    def show_thanks(self):
        """Show special thanks window"""
        thanks = QMessageBox()  # No parent to avoid threading issues
        thanks.setWindowTitle("Special Thanks")
        thanks.setStyleSheet(self.get_messagebox_stylesheet())
        thanks.setText(
            "Special Thanks\n\n"
            "Ardishco (github.com/raidenovich)\n"
            "Deviaze\n"
            "Kemal\n"
            "Jacazimbo <3\n"
            "Kharoon\n"
            "Jediclank134"
        )
        thanks.setStandardButtons(QMessageBox.StandardButton.Ok)
        thanks.exec()


def main():
    """Main entry point"""
    import time as time_module

    total_start_time = time_module.time()

    if platform.system() != "Linux":
        app = QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "Unsupported Platform",
            "This installer is designed for Linux systems only.",
        )
        return

    app_init_start = time_module.time()
    app = QApplication(sys.argv)
    app_init_time = time_module.time() - app_init_start

    window_init_start = time_module.time()
    window = AffinityInstallerGUI()
    window_init_time = time_module.time() - window_init_start

    # Show window immediately - slow operations will run in background
    window.show()

    # Process events to ensure window is displayed before background tasks start
    app.processEvents()

    total_init_time = time_module.time() - total_start_time
    print(f"\n[Startup Timing] QApplication init: {app_init_time:.3f}s")
    print(f"[Startup Timing] Window init: {window_init_time:.3f}s")
    print(f"[Startup Timing] Total startup: {total_init_time:.3f}s")
    print(f"[Startup Timing] Window shown immediately - background tasks running...\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
