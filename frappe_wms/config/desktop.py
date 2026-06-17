from frappe import _


def get_data():
    return [
        {
            "module_name": "WMS",
            "type": "module",
            "label": _("WMS"),
            "icon": "octicon octicon-package",
            "color": "grey",
        }
    ]
