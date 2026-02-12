#!/usr/bin/env python3
import os
import webbrowser
import re
import html
try:
    import tomllib 
except ImportError:  
    tomllib = None
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
import threading
import shutil

from rune.api.aur import AURClient
from rune.core.installer import PackageInstaller
from rune.core.pacman import (
    list_installed_aur,
    list_aur_updates,
    list_core_extra_updates,
    list_all_installed_packages,
    list_explicit_installed_packages,
    list_orphan_packages,
    RepoPackage,
)
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
        self.aur_enabled = False
        self.default_installed_filter = "all"
        self.max_search_results = 100
        
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
        self._ensure_yay_helper()
        self.connect("destroy", Gtk.main_quit)

    def _apply_aur_preferences(self) -> None:
        name = self.stack.get_visible_child_name() if hasattr(self, "stack") else None

        if name == "search":
            for child in self.search_listbox.get_children():
                self.search_listbox.remove(child)
            self.search_packages = []
            if self.aur_enabled:
                self.search_status_label.set_text("Enter a search term to find AUR packages")
            else:
                self.search_status_label.set_text("AUR packages are disabled in preferences")

        if name == "installed" and self.installed_loaded:
            self._on_refresh_installed(None)

        if name == "updates" and self.updates_loaded:
            self._on_refresh_updates(None)

    def _create_settings_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        item_prefs = Gtk.MenuItem(label="Preferences")
        item_prefs.connect("activate", lambda *_: self._show_preferences())
        menu.append(item_prefs)

        item_about = Gtk.MenuItem(label="About")
        item_about.connect("activate", lambda *_: self._show_about())
        menu.append(item_about)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(item_quit)

        menu.show_all()
        return menu

    def _show_preferences(self) -> None:
        dialog = Gtk.Dialog(title="Preferences", transient_for=self, modal=True)
        dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        content = dialog.get_content_area()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_border_width(10)

        aur_frame = Gtk.Frame(label="AUR and Repositories")
        aur_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        aur_box.set_border_width(6)

        aur_checkbox = Gtk.CheckButton(label="Enable AUR packages")
        aur_checkbox.set_active(self.aur_enabled)
        aur_box.pack_start(aur_checkbox, False, False, 0)

        installed_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        installed_label = Gtk.Label(label="Default Installed filter:")
        installed_label.set_halign(Gtk.Align.START)
        installed_combo = Gtk.ComboBoxText()
        installed_combo.append("all", "All")
        installed_combo.append("explicit", "Explicit")
        installed_combo.append("orphans", "Orphans")
        installed_combo.append("foreign", "Foreign (AUR)")
        installed_combo.set_active_id(self.default_installed_filter)
        installed_box.pack_start(installed_label, False, False, 0)
        installed_box.pack_start(installed_combo, False, False, 0)
        aur_box.pack_start(installed_box, False, False, 0)

        aur_frame.add(aur_box)
        vbox.pack_start(aur_frame, False, False, 0)

        search_frame = Gtk.Frame(label="Search")
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.set_border_width(6)

        max_label = Gtk.Label(label="Maximum search results:")
        max_label.set_halign(Gtk.Align.START)
        adjustment = Gtk.Adjustment(float(self.max_search_results), 10.0, 1000.0, 10.0, 50.0, 0.0)
        max_spin = Gtk.SpinButton()
        max_spin.set_adjustment(adjustment)
        max_spin.set_digits(0)
        search_box.pack_start(max_label, False, False, 0)
        search_box.pack_start(max_spin, False, False, 0)

        search_frame.add(search_box)
        vbox.pack_start(search_frame, False, False, 0)

        content.add(vbox)
        dialog.show_all()

        def on_response(dlg, response):
            self.aur_enabled = aur_checkbox.get_active()
            self.default_installed_filter = installed_combo.get_active_id() or "all"
            self.max_search_results = int(max_spin.get_value())
            dlg.destroy()
            if hasattr(self, "installed_filter") and self.installed_filter is not None:
                self.installed_filter.set_active_id(self.default_installed_filter)
            self._apply_aur_preferences()

        dialog.connect("response", on_response)

    def _show_about(self) -> None:
        dialog = Gtk.Dialog(title="About Runa", transient_for=self, modal=True)
        dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        content = dialog.get_content_area()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_border_width(10)

        logo = self._load_logo_image()
        if logo is not None:
            logo.set_halign(Gtk.Align.CENTER)
            vbox.pack_start(logo, False, False, 0)

        title_label = Gtk.Label()
        title_label.set_markup("<big><b>Runa</b></big>")
        title_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(title_label, False, False, 0)

        version = self._load_version()
        if version:
            version_label = Gtk.Label(label=f"Version {version}")
            version_label.set_halign(Gtk.Align.CENTER)
            vbox.pack_start(version_label, False, False, 0)

        desc_label = Gtk.Label(label="A graphical AUR and repository package manager for Arch Linux.")
        desc_label.set_line_wrap(True)
        desc_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(desc_label, False, False, 0)

        buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        source_button = Gtk.Button()
        source_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        source_label = Gtk.Label(label="Source Code")
        source_label.set_halign(Gtk.Align.START)
        source_box.pack_start(source_label, True, True, 0)
        source_image = Gtk.Image.new_from_icon_name("external-link-symbolic", Gtk.IconSize.MENU)
        source_image.set_pixel_size(12)
        source_image.set_halign(Gtk.Align.END)
        source_box.pack_start(source_image, False, False, 0)
        source_button.add(source_box)
        source_button.connect("clicked", lambda *_: webbrowser.open("https://github.com/Rune-Linux/Runa"))
        buttons_box.pack_start(source_button, False, False, 0)

        legal_button = Gtk.Button(label="Legal")
        legal_button.connect("clicked", lambda *_: self._show_legal())
        buttons_box.pack_start(legal_button, False, False, 0)

        vbox.pack_start(buttons_box, False, False, 0)

        content.add(vbox)
        dialog.show_all()

        dialog.connect("response", lambda dlg, resp: dlg.destroy())

    def _show_legal(self) -> None:
        text = self._load_license_text()
        markup = self._license_to_markup(text)

        dialog = Gtk.Dialog(title="Legal Information", transient_for=self, modal=True)
        dialog.set_default_size(500, 350)
        dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        content = dialog.get_content_area()
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_width(500)
        scrolled.set_min_content_height(300)

        label = Gtk.Label()
        label.set_use_markup(True)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_xalign(0.0)
        label.set_selectable(True)
        label.set_markup(markup)

        def on_activate_link(widget, uri):
            webbrowser.open(uri)
            return True

        label.connect("activate-link", on_activate_link)

        scrolled.add(label)
        content.add(scrolled)
        dialog.show_all()

        dialog.connect("response", lambda dlg, resp: dlg.destroy())

    def _load_license_text(self) -> str:
        dir_path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(6):
            candidate = os.path.join(dir_path, "LICENSE")
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    break
            parent = os.path.dirname(dir_path)
            if parent == dir_path:
                break
            dir_path = parent
        return "LICENSE file not found."

    def _load_version(self) -> str:
        if tomllib is None:
            return ""

        dir_path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(6):
            candidate = os.path.join(dir_path, "pyproject.toml")
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "rb") as f:
                        data = tomllib.load(f)
                    version = data.get("project", {}).get("version")
                    if version:
                        return str(version)
                except Exception:
                    break
            parent = os.path.dirname(dir_path)
            if parent == dir_path:
                break
            dir_path = parent
        return ""

    def _license_to_markup(self, text: str) -> str:
        pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        parts = []
        last_index = 0

        for match in pattern.finditer(text):
            before = text[last_index:match.start()]
            parts.append(html.escape(before))

            link_text = html.escape(match.group(1))
            href = html.escape(match.group(2), quote=True)
            parts.append(f'<a href="{href}">{link_text}</a>')

            last_index = match.end()

        remaining = text[last_index:]
        parts.append(html.escape(remaining))

        return "".join(parts)

    def _load_logo_image(self):
        dir_path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(6):
            candidate = os.path.join(dir_path, "assets", "logo.png")
            if os.path.isfile(candidate):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(candidate, 96, 96, True)
                    return Gtk.Image.new_from_pixbuf(pixbuf)
                except Exception:
                    break
            parent = os.path.dirname(dir_path)
            if parent == dir_path:
                break
            dir_path = parent
        return None

    def _ensure_yay_helper(self) -> None:
        if shutil.which("yay") is not None:
            return

        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Install yay AUR helper?",
        )
        dialog.format_secondary_text(
            "The 'yay' AUR helper is not installed. Runa can install it using pacman. "
            "This is optional, but recommended if you want to use yay alongside Runa.\n\n"
            "Do you want to install yay now?",
        )
        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.YES:
            return

        password_dialog = PasswordDialog(self)
        response = password_dialog.run()
        password = password_dialog.get_password()
        password_dialog.destroy()

        if response != Gtk.ResponseType.OK or not password:
            return

        def worker() -> None:
            success = self.installer.install_yay(password)

            def finish() -> None:
                if success:
                    msg = Gtk.MessageDialog(
                        transient_for=self,
                        modal=True,
                        message_type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.OK,
                        text="yay has been installed successfully.",
                    )
                else:
                    msg = Gtk.MessageDialog(
                        transient_for=self,
                        modal=True,
                        message_type=Gtk.MessageType.ERROR,
                        buttons=Gtk.ButtonsType.OK,
                        text="Failed to install yay.",
                    )
                msg.run()
                msg.destroy()

            GLib.idle_add(finish)

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
    
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

        menu_button = Gtk.MenuButton()
        menu_icon = Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        menu_button.add(menu_icon)
        menu_button.set_popup(self._create_settings_menu())

        header_box.pack_end(menu_button, False, False, 0)
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

        self.sort_order = Gtk.ComboBoxText()
        self.sort_order.append("popularity-desc", "Most popular first")
        self.sort_order.append("popularity-asc", "Least popular first")
        self.sort_order.set_active(0)
        self.sort_order.connect("changed", self._on_sort_order_changed)
        search_box.pack_start(self.sort_order, False, False, 0)
        
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
        
        self.installed_filter = Gtk.ComboBoxText()
        self.installed_filter.append("all", "All")
        self.installed_filter.append("explicit", "Explicit")
        self.installed_filter.append("orphans", "Orphans")
        self.installed_filter.append("foreign", "Foreign")
        self.installed_filter.set_active_id(self.default_installed_filter)
        self.installed_filter.connect("changed", self._on_installed_filter_changed)
        toolbar.pack_start(self.installed_filter, False, False, 0)
        
        self.installed_status_label = Gtk.Label(label="Installed packages will be listed here")
        self.installed_status_label.set_halign(Gtk.Align.START)
        toolbar.pack_start(self.installed_status_label, True, True, 0)
        
        box.pack_start(toolbar, False, False, 0)
        
        results_frame = Gtk.Frame(label="Installed Packages")
        
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
        if not self.aur_enabled:
            self.search_status_label.set_text("AUR packages are disabled in preferences")
            return
        self.search_status_label.set_text("Searching...")
        self.search_entry.set_sensitive(False)
        
        def search_thread():
            try:
                search_by = self.search_type.get_active_id() or "name-desc"
                if query:
                    if len(query) < 2:
                        GLib.idle_add(self._display_results, [], "Search term must be at least 2 characters")
                        return
                    results = self.aur_client.search(query, by=search_by)
                else:
                    results = self.aur_client.search_popular(by=search_by, limit=self.max_search_results)
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

        self._apply_sort_and_display()

    def _apply_sort_and_display(self) -> None:
        for child in self.search_listbox.get_children():
            self.search_listbox.remove(child)

        if not self.search_packages:
            self.search_status_label.set_text("No packages found")
            return

        sort_id = None
        if hasattr(self, "sort_order") and self.sort_order is not None:
            sort_id = self.sort_order.get_active_id()

        packages = list(self.search_packages)

        if sort_id == "popularity-asc":
            packages.sort(key=lambda p: (getattr(p, "popularity", 0.0), getattr(p, "votes", 0)))
        else:
            packages.sort(key=lambda p: (getattr(p, "popularity", 0.0), getattr(p, "votes", 0)), reverse=True)

        limit = max(1, int(self.max_search_results)) if hasattr(self, "max_search_results") else 100

        for package in packages[:limit]:
            row = PackageRow(package)
            self.search_listbox.add(row)

        self.search_listbox.show_all()

        count = len(packages)
        shown = min(count, limit)
        if count > limit:
            self.search_status_label.set_text(f"Found {count} packages (showing first {shown}, sorted by popularity)")
        else:
            self.search_status_label.set_text(f"Found {count} packages (sorted by popularity)")

    def _on_sort_order_changed(self, widget) -> None:
        if not getattr(self, "search_packages", None):
            return
        self._apply_sort_and_display()
    
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
        self.installed_status_label.set_text("Loading installed packages...")
        
        def worker():
            try:
                filter_id = None
                if hasattr(self, "installed_filter") and self.installed_filter is not None:
                    filter_id = self.installed_filter.get_active_id()

                if filter_id == "all":
                    packages = list_all_installed_packages()
                elif filter_id == "explicit":
                    packages = list_explicit_installed_packages()
                elif filter_id == "orphans":
                    packages = list_orphan_packages()
                elif filter_id == "foreign" and self.aur_enabled:
                    packages = list_installed_aur()
                else:
                    packages = []
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
            self.installed_status_label.set_text("No packages found for this filter")
            return
        
        for package in packages:
            row = PackageRow(package)
            self.installed_listbox.add(row)
        
        self.installed_listbox.show_all()
        self.installed_status_label.set_text(f"Found {len(packages)} installed package(s)")

    def _on_installed_filter_changed(self, widget) -> None:
        if self.installed_loaded:
            self._on_refresh_installed(None)
    
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
            aur_packages = []
            repo_packages = []
            errors = []

            if self.aur_enabled:
                try:
                    aur_packages = list_aur_updates()
                except Exception as e:
                    errors.append(str(e))

            try:
                repo_packages = list_core_extra_updates()
            except Exception as e:
                errors.append(str(e))

            error_msg = None
            if not aur_packages and not repo_packages and errors:
                error_msg = "; ".join(errors)

            GLib.idle_add(self._display_updates, aur_packages, repo_packages, error_msg)
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
            msg = str(error)
            lower = msg.lower()
            if "no packages" in lower or "pacman command failed" in lower:
                self.updates_status_label.set_text("No packages found")
            else:
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
