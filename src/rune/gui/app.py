#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import threading

from rune.api.aur import AURClient
from rune.core.installer import PackageInstaller
from rune.core.pacman import list_installed_aur, list_aur_updates, list_core_extra_updates, RepoPackage
from rune.gui.dialogs import PasswordDialog, InstallProgressDialog
from rune.gui.widgets import PackageRow


class RuneAURHelper(Gtk.Window):
    def __init__(self):
        super().__init__(title="Runa")
        
        self.set_default_size(900, 600)
        self.set_border_width(10)
        
        self.aur_client = AURClient()
        self.installer = PackageInstaller()
        self.search_packages = []
        self.installed_packages = []
        self.update_aur_packages = []
        self.update_repo_packages = []
        self.installed_loaded = False
        self.updates_loaded = False
        
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
        title.set_markup("<big><b>Runa</b></big>")
        title.set_halign(Gtk.Align.START)
        header_box.pack_start(title, False, False, 0)
        
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)
        
        stack_switcher = Gtk.StackSwitcher()
        stack_switcher.set_stack(self.stack)
        header_box.pack_end(stack_switcher, False, False, 0)
        
        main_box.pack_start(header_box, False, False, 0)
        
        search_page = self._build_search_page()
        installed_page = self._build_installed_page()
        updates_page = self._build_updates_page()
        
        self.stack.add_titled(search_page, "search", "Search")
        self.stack.add_titled(installed_page, "installed", "Installed")
        self.stack.add_titled(updates_page, "updates", "Updates")
        
        self.stack.connect("notify::visible-child-name", self._on_stack_page_changed)
        
        main_box.pack_start(self.stack, True, True, 0)
        
        self.add(main_box)
    
    def _build_search_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
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
        
        box.pack_start(search_box, False, False, 0)
        
        results_frame = Gtk.Frame(label="Search Results")
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(300)
        
        self.search_listbox = Gtk.ListBox()
        self.search_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.search_listbox)
        
        results_frame.add(scrolled)
        box.pack_start(results_frame, True, True, 0)
        
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.search_status_label = Gtk.Label(label="Enter a search term to find AUR packages")
        self.search_status_label.set_halign(Gtk.Align.START)
        action_box.pack_start(self.search_status_label, True, True, 0)
        
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
        
        box.pack_start(action_box, False, False, 0)
        
        return box
    
    def _build_installed_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.installed_refresh_button = Gtk.Button(label="Refresh")
        self.installed_refresh_button.connect("clicked", self._on_refresh_installed)
        toolbar.pack_start(self.installed_refresh_button, False, False, 0)
        
        self.installed_status_label = Gtk.Label(label="Installed AUR packages will be listed here")
        self.installed_status_label.set_halign(Gtk.Align.START)
        toolbar.pack_start(self.installed_status_label, True, True, 0)
        
        box.pack_start(toolbar, False, False, 0)
        
        results_frame = Gtk.Frame(label="Installed AUR Packages")
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(300)
        
        self.installed_listbox = Gtk.ListBox()
        self.installed_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.installed_listbox)
        
        results_frame.add(scrolled)
        box.pack_start(results_frame, True, True, 0)
        
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        select_all_btn = Gtk.Button(label="Select All")
        select_all_btn.connect("clicked", self._on_installed_select_all)
        action_box.pack_start(select_all_btn, False, False, 0)
        
        select_none_btn = Gtk.Button(label="Select None")
        select_none_btn.connect("clicked", self._on_installed_select_none)
        action_box.pack_start(select_none_btn, False, False, 0)
        
        remove_button = Gtk.Button(label="Remove Selected")
        remove_button.connect("clicked", self._on_remove_installed)
        action_box.pack_start(remove_button, False, False, 0)
        
        box.pack_start(action_box, False, False, 0)
        
        return box
    
    def _build_updates_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.updates_refresh_button = Gtk.Button(label="Check for Updates")
        self.updates_refresh_button.connect("clicked", self._on_refresh_updates)
        toolbar.pack_start(self.updates_refresh_button, False, False, 0)
        
        self.updates_status_label = Gtk.Label(label="AUR updates will be listed here")
        self.updates_status_label.set_halign(Gtk.Align.START)
        toolbar.pack_start(self.updates_status_label, True, True, 0)
        
        box.pack_start(toolbar, False, False, 0)
        
        results_frame = Gtk.Frame(label="AUR and Repo Updates")
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(300)
        
        self.updates_listbox = Gtk.ListBox()
        self.updates_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.updates_listbox)
        
        results_frame.add(scrolled)
        box.pack_start(results_frame, True, True, 0)
        
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        select_all_btn = Gtk.Button(label="Select All")
        select_all_btn.connect("clicked", self._on_updates_select_all)
        action_box.pack_start(select_all_btn, False, False, 0)
        
        select_none_btn = Gtk.Button(label="Select None")
        select_none_btn.connect("clicked", self._on_updates_select_none)
        action_box.pack_start(select_none_btn, False, False, 0)
        
        update_selected_button = Gtk.Button(label="Update Selected")
        update_selected_button.connect("clicked", self._on_update_selected)
        action_box.pack_start(update_selected_button, False, False, 0)
        
        update_all_button = Gtk.Button(label="Update All")
        update_all_button.connect("clicked", self._on_update_all)
        action_box.pack_start(update_all_button, False, False, 0)
        
        box.pack_start(action_box, False, False, 0)
        
        return box
    
    def _on_stack_page_changed(self, stack, param) -> None:
        name = stack.get_visible_child_name()
        if name == "installed" and not self.installed_loaded:
            self.installed_loaded = True
            self._on_refresh_installed(None)
        elif name == "updates" and not self.updates_loaded:
            self.updates_loaded = True
            self._on_refresh_updates(None)
    
    def _on_search(self, widget) -> None:
        query = self.search_entry.get_text().strip()
        if not query:
            return
        
        if len(query) < 2:
            self.search_status_label.set_text("Search term must be at least 2 characters")
            return
        
        self.search_status_label.set_text("Searching...")
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
        
        for child in self.search_listbox.get_children():
            self.search_listbox.remove(child)
        
        self.search_packages = packages
        
        if error:
            self.search_status_label.set_text(f"Error: {error}")
            return
        
        if not packages:
            self.search_status_label.set_text("No packages found")
            return
        
        for package in packages[:100]:  
            row = PackageRow(package)
            self.search_listbox.add(row)
        
        self.search_listbox.show_all()
        
        count = len(packages)
        shown = min(count, 100)
        if count > 100:
            self.search_status_label.set_text(f"Found {count} packages (showing first {shown})")
        else:
            self.search_status_label.set_text(f"Found {count} packages")
    
    def _get_selected_search_packages(self) -> list:
        selected = []
        for row in self.search_listbox.get_children():
            if isinstance(row, PackageRow) and row.is_selected():
                selected.append(row.package)
        return selected
    
    def _on_select_all(self, widget) -> None:
        for row in self.search_listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(True)
    
    def _on_select_none(self, widget) -> None:
        for row in self.search_listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(False)
    
    def _on_install(self, widget) -> None:
        selected = self._get_selected_search_packages()
        
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
        
        progress_dialog = InstallProgressDialog(self, selected, operation_name="Installing")
        
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

    def _on_refresh_installed(self, widget) -> None:
        if hasattr(self, "installed_refresh_button") and self.installed_refresh_button:
            self.installed_refresh_button.set_sensitive(False)
        self.installed_status_label.set_text("Loading installed AUR packages...")
        
        def worker():
            try:
                packages = list_installed_aur()
                GLib.idle_add(self._display_installed_packages, packages, None)
            except Exception as e:
                GLib.idle_add(self._display_installed_packages, [], str(e))
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
    
    def _display_installed_packages(self, packages, error) -> None:
        if hasattr(self, "installed_refresh_button") and self.installed_refresh_button:
            self.installed_refresh_button.set_sensitive(True)
        
        for child in self.installed_listbox.get_children():
            self.installed_listbox.remove(child)
        
        self.installed_packages = packages
        
        if error:
            self.installed_status_label.set_text(f"Error: {error}")
            return
        
        if not packages:
            self.installed_status_label.set_text("No AUR packages installed")
            return
        
        for package in packages:
            row = PackageRow(package)
            self.installed_listbox.add(row)
        
        self.installed_listbox.show_all()
        self.installed_status_label.set_text(f"Found {len(packages)} installed AUR packages")
    
    def _get_selected_installed_packages(self) -> list:
        selected = []
        for row in self.installed_listbox.get_children():
            if isinstance(row, PackageRow) and row.is_selected():
                selected.append(row.package)
        return selected
    
    def _on_installed_select_all(self, widget) -> None:
        for row in self.installed_listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(True)
    
    def _on_installed_select_none(self, widget) -> None:
        for row in self.installed_listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(False)
    
    def _on_remove_installed(self, widget) -> None:
        selected = self._get_selected_installed_packages()
        if not selected:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="No packages selected"
            )
            dialog.format_secondary_text("Please select one or more packages to remove.")
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
            text=f"Remove {len(selected)} package(s)?"
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
        progress_dialog = InstallProgressDialog(self, selected, operation_name="Removing")
        
        def remove_thread():
            names = [p.name for p in selected]
            results = {"success": [], "failed": []}
            try:
                self.installer.remove_packages(names, password, log_callback=progress_dialog.log)
                results["success"] = names
            except Exception as e:
                for name in names:
                    results["failed"].append((name, str(e)))
            progress_dialog.finish(results)
        
        thread = threading.Thread(target=remove_thread)
        thread.daemon = True
        thread.start()
        
        progress_dialog.run()
        progress_dialog.destroy()
        self._on_refresh_installed(None)
        self.updates_loaded = False
    
    def _on_refresh_updates(self, widget) -> None:
        if hasattr(self, "updates_refresh_button") and self.updates_refresh_button:
            self.updates_refresh_button.set_sensitive(False)
        self.updates_status_label.set_text("Checking for AUR and repo updates...")
        
        def worker():
            try:
                aur_packages = list_aur_updates()
                repo_packages = list_core_extra_updates()
                GLib.idle_add(self._display_updates, aur_packages, repo_packages, None)
            except Exception as e:
                GLib.idle_add(self._display_updates, [], [], str(e))
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
    
    def _display_updates(self, aur_packages, repo_packages, error) -> None:
        if hasattr(self, "updates_refresh_button") and self.updates_refresh_button:
            self.updates_refresh_button.set_sensitive(True)
        
        for child in self.updates_listbox.get_children():
            self.updates_listbox.remove(child)
        
        self.update_aur_packages = aur_packages
        self.update_repo_packages = repo_packages
        
        if error:
            self.updates_status_label.set_text(f"Error: {error}")
            return
        
        combined = list(aur_packages) + list(repo_packages)
        if not combined:
            self.updates_status_label.set_text("No AUR or repo updates available")
            return
        
        for package in combined:
            row = PackageRow(package)
            self.updates_listbox.add(row)
        
        self.updates_listbox.show_all()
        self.updates_status_label.set_text(
            f"Found {len(aur_packages)} AUR and {len(repo_packages)} repo update(s)"
        )
    
    def _get_selected_update_packages(self) -> list:
        selected = []
        for row in self.updates_listbox.get_children():
            if isinstance(row, PackageRow) and row.is_selected():
                selected.append(row.package)
        return selected
    
    def _on_updates_select_all(self, widget) -> None:
        for row in self.updates_listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(True)
    
    def _on_updates_select_none(self, widget) -> None:
        for row in self.updates_listbox.get_children():
            if isinstance(row, PackageRow):
                row.set_selected(False)
    
    def _on_update_selected(self, widget) -> None:
        selected = self._get_selected_update_packages()
        if not selected:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="No packages selected"
            )
            dialog.format_secondary_text("Please select one or more packages to update.")
            dialog.run()
            dialog.destroy()
            return
        self._run_update_flow(selected)
    
    def _on_update_all(self, widget) -> None:
        combined = list(self.update_aur_packages) + list(self.update_repo_packages)
        if not combined:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="No updates available"
            )
            dialog.format_secondary_text("There are no updates to install.")
            dialog.run()
            dialog.destroy()
            return
        self._run_update_flow(combined)
    
    def _run_update_flow(self, packages) -> None:
        pkg_names = ", ".join(p.name for p in packages[:5])
        if len(packages) > 5:
            pkg_names += f" and {len(packages) - 5} more"
        confirm = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Update {len(packages)} package(s)?"
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
        progress_dialog = InstallProgressDialog(self, packages, operation_name="Updating")
        
        def update_thread():
            aur_packages = [p for p in packages if not isinstance(p, RepoPackage)]
            repo_packages = [p for p in packages if isinstance(p, RepoPackage)]
            results = {"success": [], "failed": []}
            if aur_packages:
                aur_result = self.installer.install_multiple(
                    aur_packages,
                    password,
                    log_callback=progress_dialog.log,
                    progress_callback=progress_dialog.set_progress,
                )
                results["success"].extend(aur_result["success"])
                results["failed"].extend(aur_result["failed"])
            if repo_packages:
                names = [p.name for p in repo_packages]
                try:
                    self.installer.update_repo_packages(
                        names,
                        password,
                        log_callback=progress_dialog.log,
                    )
                    results["success"].extend(names)
                except Exception as e:
                    for name in names:
                        results["failed"].append((name, str(e)))
            progress_dialog.finish(results)
        
        thread = threading.Thread(target=update_thread)
        thread.daemon = True
        thread.start()
        
        progress_dialog.run()
        progress_dialog.destroy()
        self._on_refresh_updates(None)
        self.installed_loaded = False


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
