import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as Keyboard from 'resource:///org/gnome/shell/ui/status/keyboard.js';

const IFACE = `
<node>
  <interface name="com.switchamba.LayoutSwitcher">
    <method name="SwitchTo">
      <arg type="u" direction="in" name="index"/>
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="GetCurrent">
      <arg type="u" direction="out" name="index"/>
    </method>
    <method name="SetActive">
      <arg type="b" direction="in" name="active"/>
    </method>
  </interface>
</node>`;

// Colors for each layout
const LAYOUT_COLORS = {
    0: '#6AACF0', // EN - blue
    1: '#F07070', // RU - red
    2: '#FFDA44', // UA - yellow
};

const LAYOUT_LABELS = {
    0: 'A',
    1: 'Я',
    2: 'І',
};

let _dbus = null;
let _indicator = null;

class LayoutSwitcherDBus {
    constructor() {
        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbusImpl.export(Gio.DBus.session, '/com/switchamba/LayoutSwitcher');
    }

    SwitchTo(index) {
        try {
            const ism = Keyboard.getInputSourceManager();
            const source = ism.inputSources[index];
            if (source) {
                source.activate(true);
                if (_indicator)
                    _indicator.updateLayout(index);
                return true;
            }
            return false;
        } catch(e) {
            log(`Switchamba: ${e}`);
            return false;
        }
    }

    GetCurrent() {
        try {
            const ism = Keyboard.getInputSourceManager();
            return ism.currentSource ? ism.currentSource.index : 0;
        } catch(e) {
            return 0;
        }
    }

    SetActive(active) {
        if (_indicator)
            _indicator.setActive(active);
    }

    destroy() {
        this._dbusImpl.unexport();
    }
}

const SwitchambaIndicator = GObject.registerClass(
class SwitchambaIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Switchamba', false);

        this._box = new St.BoxLayout({style_class: 'panel-status-indicators-box'});

        // Icon showing current auto-detected layout
        this._label = new St.Label({
            text: 'S',
            y_align: Clutter.ActorAlign.CENTER,
            style: 'font-weight: bold; font-size: 13px; color: #6AACF0; margin: 0 2px;',
        });
        this._box.add_child(this._label);

        // Status dot (green = active, grey = inactive)
        this._dot = new St.Label({
            text: '\u25CF', // ●
            y_align: Clutter.ActorAlign.CENTER,
            style: 'font-size: 8px; color: #888888; margin-left: 1px;',
        });
        this._box.add_child(this._dot);

        this.add_child(this._box);

        // Listen for layout changes
        this._ism = Keyboard.getInputSourceManager();
        this._signalId = this._ism.connect('current-source-changed',
            this._onSourceChanged.bind(this));

        // Set initial state
        if (this._ism.currentSource)
            this.updateLayout(this._ism.currentSource.index);
    }

    _onSourceChanged(ism) {
        if (ism.currentSource)
            this.updateLayout(ism.currentSource.index);
    }

    updateLayout(index) {
        const label = LAYOUT_LABELS[index] || '?';
        const color = LAYOUT_COLORS[index] || '#FFFFFF';
        this._label.set_text(label);
        this._label.set_style(
            `font-weight: bold; font-size: 13px; color: ${color}; margin: 0 2px;`
        );
    }

    setActive(active) {
        if (active) {
            this._dot.set_style('font-size: 8px; color: #73d216; margin-left: 1px;');
        } else {
            this._dot.set_style('font-size: 8px; color: #888888; margin-left: 1px;');
        }
    }

    _onDestroy() {
        if (this._signalId && this._ism) {
            this._ism.disconnect(this._signalId);
            this._signalId = null;
        }
        super._onDestroy();
    }
});

export default class SwitchambaExtension {
    enable() {
        _dbus = new LayoutSwitcherDBus();
        _indicator = new SwitchambaIndicator();
        // Add to right side of panel, position 1 (next to keyboard indicator)
        Main.panel.addToStatusArea('switchamba', _indicator, 1, 'right');
    }

    disable() {
        if (_dbus) {
            _dbus.destroy();
            _dbus = null;
        }
        if (_indicator) {
            _indicator.destroy();
            _indicator = null;
        }
    }
}
