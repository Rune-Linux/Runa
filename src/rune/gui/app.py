#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import threading

from rune.api.aur import AURClient
from rune.core.installer import PackageInstaller
from rune.gui.dialogs import PasswordDialog, InstallProgressDialog
from rune.gui.widgets import PackageRow


class RuneAURHelper(Gtk.Window):
    def __init__(self):
        super().__init__(title="Rune AUR Helper")
        
        self.set_default_size(900, 600)
        self.set_border_width(10)
        
        self.aur_client = AURClient()
        self.installer = PackageInstaller()
        self.packages = []
        
        missing = self.installer.check_dependencies()
        if missing:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=f"Missing required tools: {', '.join(missing)}"
            )
            dialog.run()
            dialog.destroy()
        
        self._setup_ui()
        self.connect("destroy", Gtk.main_quit)
    
    def _setup_ui(self) -> None:
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        title = Gtk.Label()
        title.set_markup("<big><b>Rune AUR Helper</b></big>")
        title.set_halign(Gtk.Align.START)
        header_box.pack_start(title, False, False, 0)
        
        main_box.pack_start(header_box, False, False, 0)
        
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Search AUR packages...")
        self.search_entry.connect("activate", self._on_search)
        search_box.pack_start(self.search_entry, True, True, 0)
        
        self.search_type = Gtk.ComboBoxText()
        self.search_type.append("name-desc", "Name & Description")
        self.search_type.append("name", "Name Only")
        self.search_type.append("keywords", "Keywords")
        self.search_type.append("maintainer", "Maintainer")
        self.search_type.set_active(0)
        search_box.pack_start(self.search_type, False, False, 0)
        
        search_button = Gtk.Button(label="Search")
        search_button.connect("clicked", self._on_search)
        search_box.pack_start(search_button, False, False, 0)
        
        main_box.pack_start(search_box, False, False, 0)
        
        results_frame = Gtk.Frame(label="Search Results")
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(300)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.listbox)
        
        results_frame.add(scrolled)
        main_box.pack_start(results_frame, True, True, 0)
        
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.status_label = Gtk.Label(label="Enter a search term to find AUR packages")
        self.status_label.set_halign(Gtk.Align.START)
        action_box.pack_start(self.status_label, True, True, 0)
        
        select_all_btn = Gtk.Button(label="Select All")
        select_all_btn.connect("clicked", self._on_select_all)
        action_box.pack_start(select_all_btn, False, False, 0)
        
        select_none_btn = Gtk.Button(label="Select None")
        select_none_btn.connect("clicked", self._on_select_none)
        action_box.pack_start(select_none_btn, False, False, 0)
        
        self.install_button = Gtk.Button(label="Install Selected")
        self.install_button.get_style_context().add_class("suggested-action")
        self.install_button.connect("clicked", self._on_install)
        action_box.pack_start(self.install_button, False, False, 0)
        
        main_box.pack_start(action_box, False, False, 0)
        
        self.add(main_box)
    
    def _on_search(self, widget) -> None:
        query = self.search_entry.get_text().strip()
        if not query:
            return
        
        if len(query) < 2:
            self.status_label.set_text("Search term must be at least 2 characters")
            return
        
        self.status_label.set_text("Searching...")
        self.search_entry.set_sensitive(False)
        
        def search_thread():
            try:
                search_by = self.search_type.get_active_id()
                results = self.aur_client.search(query, by=search_by)
                GLib.idle_add(self._display_results, results, None)
            except Exception as e:
                GLib.idle_add(self._display_results, [], str(e))
        
        thread = threading.Thread(target=search_thread)
        thread.daemon = True
        thread.start()
    
    def _display_results(self, packages, error) -> None:
        self.search_entry.set_sensitive(True)
        
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        
        self.packages = packages
        
        if error:
            self.status_label.set_text(f"Error: {error}")
            return
        
        if not packages:
            self.status_label.set_text("No packages found")
            return
        
        for package in packages[:100]:  # Limit to 100 results
            row = PackageRow(package)
            self.listbox.add(row)
        
        self.listbox.show_all()
        
        count = len(packages)
        shown = min(count, 100)
        if count > 100:
            self.status_label.set_text(f"Found {count} packages (showing first {shown})")
        else:
            self.status_label.set_text(f"Found {count} packages")
    
    def _get_selected_packages(self) -> list:
        selected = []
        for row in self.listbox.get_children():
            if isinstance(row, PackageRow) and row.is_selected():
                selected.append(row.package)
        return selected
    
    def _on_select_all(self, widget) -> None:
        for row in self.listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(True)
    
    def _on_select_none(self, widget) -> None:
        for row in self.listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(False)
    
    def _on_install(self, widget) -> None:
        selected = self._get_selected_packages()
        
        if not selected:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="No packages selected"
            )
            dialog.format_secondary_text("Please select one or more packages to install.")
            dialog.run()
            dialog.destroy()
            return
        
        pkg_names = ", ".join(p.name for p in selected[:5])
        if len(selected) > 5:
            pkg_names += f" and {len(selected) - 5} more"
        
        confirm = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Install {len(selected)} package(s)?"
        )
        confirm.format_secondary_text(f"Packages: {pkg_names}")
        response = confirm.run()
        confirm.destroy()
        
        if response != Gtk.ResponseType.YES:
            return
        
        password_dialog = PasswordDialog(self)
        response = password_dialog.run()
        password = password_dialog.get_password()
        password_dialog.destroy()
        
        if response != Gtk.ResponseType.OK or not password:
            return
        
        progress_dialog = InstallProgressDialog(self, selected)
        
        def install_thread():
            results = self.installer.install_multiple(
                selected,
                password,
                log_callback=progress_dialog.log,
                progress_callback=progress_dialog.set_progress
            )
            progress_dialog.finish(results)
        
        thread = threading.Thread(target=install_thread)
        thread.daemon = True
        thread.start()
        
        progress_dialog.run()
        progress_dialog.destroy()


def main():
    css = b"""
    button.suggested-action {
        background-image: linear-gradient(to bottom, #4fd1ff, #5be88a);
        background-color: transparent;
        color: #ffffff;
        border-radius: 6px;
        border-width: 0px;
        padding: 6px 12px;
    }

    button.suggested-action:hover {
        background-image: linear-gradient(to bottom, #63d7ff, #6cf29a);
    }

    button.suggested-action:active {
        background-image: linear-gradient(to bottom, #3ab7e6, #47d777);
    }
    """
    
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    
    window = RuneAURHelper()
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
