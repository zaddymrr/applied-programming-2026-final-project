import sys

from PySide6.QtWidgets import QApplication

from viewmodels.main_viewmodel import MainViewModel
from views.main_window import MainWindow


def main():
    """Assemble the MVVM application and start the Qt event loop."""
    app = QApplication(sys.argv)

    view_model = MainViewModel()
    window = MainWindow(view_model)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
