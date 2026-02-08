import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

from rune.api.aur import AURPackage
from rune.core.pacman import RepoPackage


class PackageRow(Gtk.ListBoxRow):
    def __init__(self, package):
        super().__init__()
        self.package = package
        
        self.set_margin_top(5)
        self.set_margin_bottom(5)
        self.set_margin_start(5)
        self.set_margin_end(5)
        
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_margin_top(5)
        hbox.set_margin_bottom(5)
        hbox.set_margin_start(5)
        hbox.set_margin_end(5)
        
        self.checkbox = Gtk.CheckButton()
        hbox.pack_start(self.checkbox, False, False, 0)
        
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        name_label = Gtk.Label()
        name_label.set_markup(f"<b>{GLib.markup_escape_text(package.name)}</b>")
        name_label.set_halign(Gtk.Align.START)
        name_box.pack_start(name_label, False, False, 0)
        
        version_text = package.version
        local_version = getattr(package, "local_version", None)
        if local_version and local_version != package.version:
            version_text = f"{local_version} (AUR: {package.version})"
        version_label = Gtk.Label(label=version_text)
        version_label.set_halign(Gtk.Align.START)
        version_label.get_style_context().add_class("dim-label")
        name_box.pack_start(version_label, False, False, 0)
        
        if getattr(package, "out_of_date", None):
            ood_label = Gtk.Label()
            ood_label.set_markup('<span foreground="red">[Out of Date]</span>')
            name_box.pack_start(ood_label, False, False, 0)
        
        info_box.pack_start(name_box, False, False, 0)
        
        desc_label = Gtk.Label(label=package.description or "No description")
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_line_wrap(True)
        desc_label.set_line_wrap_mode(Pango.WrapMode.WORD)
        desc_label.set_max_width_chars(80)
        desc_label.set_xalign(0)
        info_box.pack_start(desc_label, False, False, 0)
        
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        
        votes = getattr(package, "votes", None)
        popularity = getattr(package, "popularity", None)
        maintainer = getattr(package, "maintainer", None)
        repo = getattr(package, "repo", None)
        
        if votes is not None:
            votes_label = Gtk.Label()
            votes_label.set_markup(f"<small>Votes: {votes}</small>")
            stats_box.pack_start(votes_label, False, False, 0)
        
        if popularity is not None:
            pop_label = Gtk.Label()
            pop_label.set_markup(f"<small>Popularity: {float(popularity):.2f}</small>")
            stats_box.pack_start(pop_label, False, False, 0)
        
        if maintainer is not None:
            maint_label = Gtk.Label()
            maint_label.set_markup(f"<small>Maintainer: {GLib.markup_escape_text(maintainer or 'orphan')}</small>")
            stats_box.pack_start(maint_label, False, False, 0)
        elif repo is not None:
            repo_label = Gtk.Label()
            repo_label.set_markup(f"<small>Repository: {GLib.markup_escape_text(repo)}</small>")
            stats_box.pack_start(repo_label, False, False, 0)
        
        if stats_box.get_children():
            info_box.pack_start(stats_box, False, False, 0)
        
        hbox.pack_start(info_box, True, True, 0)
        
        self.add(hbox)
    
    def is_selected(self) -> bool:
        return self.checkbox.get_active()
    
    def set_selected(self, selected: bool) -> None:
        self.checkbox.set_active(selected)
