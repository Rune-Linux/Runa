import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib


class PasswordDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(
            title="Authentication Required",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True
        )
        
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        
        self.set_default_size(350, 150)
        self.set_border_width(10)
        
        box = self.get_content_area()
        box.set_spacing(10)
        
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon = Gtk.Image.new_from_icon_name("dialog-password", Gtk.IconSize.DIALOG)
        hbox.pack_start(icon, False, False, 0)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        label = Gtk.Label(label="<b>Authentication Required</b>")
        label.set_use_markup(True)
        label.set_halign(Gtk.Align.START)
        vbox.pack_start(label, False, False, 0)
        
        sub_label = Gtk.Label(label="Enter your password to install packages")
        sub_label.set_halign(Gtk.Align.START)
        vbox.pack_start(sub_label, False, False, 0)
        
        hbox.pack_start(vbox, True, True, 0)
        box.pack_start(hbox, False, False, 0)
        
        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_invisible_char('●')
        self.password_entry.set_placeholder_text("Password")
        self.password_entry.connect("activate", lambda w: self.response(Gtk.ResponseType.OK))
        box.pack_start(self.password_entry, False, False, 0)
        
        self.show_all()
        self.password_entry.grab_focus()
    
    def get_password(self) -> str:
        return self.password_entry.get_text()


class InstallProgressDialog(Gtk.Dialog):
    def __init__(self, parent, packages):
        super().__init__(
            title="Installing Packages",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True
        )
        
        self.set_default_size(600, 400)
        self.set_border_width(10)
        
        self.packages = packages
        self.cancelled = False
        
        box = self.get_content_area()
        box.set_spacing(10)
        
        self.progress_label = Gtk.Label(label=f"Installing 0/{len(packages)} packages...")
        self.progress_label.set_halign(Gtk.Align.START)
        box.pack_start(self.progress_label, False, False, 0)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        box.pack_start(self.progress_bar, False, False, 0)
        
        log_frame = Gtk.Frame(label="Output")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_buffer = self.log_view.get_buffer()
        
        scrolled.add(self.log_view)
        log_frame.add(scrolled)
        box.pack_start(log_frame, True, True, 0)
        
        self.close_button = Gtk.Button(label="Close")
        self.close_button.connect("clicked", lambda w: self.destroy())
        self.close_button.set_sensitive(False)
        box.pack_start(self.close_button, False, False, 0)
        
        self.show_all()
    
    def log(self, text: str) -> None:
        GLib.idle_add(self._log_sync, text)
    
    def _log_sync(self, text: str) -> None:
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, text + "\n")
        mark = self.log_buffer.create_mark(None, self.log_buffer.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)
    
    def set_progress(self, current: int, total: int) -> None:
        GLib.idle_add(self._set_progress_sync, current, total)
    
    def _set_progress_sync(self, current: int, total: int) -> None:
        fraction = current / total if total > 0 else 0
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(f"{current}/{total}")
        self.progress_label.set_text(f"Installing {current}/{total} packages...")
    
    def finish(self, results: dict) -> None:
        GLib.idle_add(self._finish_sync, results)
    
    def _finish_sync(self, results: dict) -> None:
        self.close_button.set_sensitive(True)
        
        success_count = len(results["success"])
        failed_count = len(results["failed"])
        
        self.progress_label.set_text(
            f"Complete: {success_count} succeeded, {failed_count} failed"
        )
        self.progress_bar.set_fraction(1.0)
        
        if results["failed"]:
            self.log("\n=== FAILED PACKAGES ===")
            for name, error in results["failed"]:
                self.log(f"  {name}: {error}")
