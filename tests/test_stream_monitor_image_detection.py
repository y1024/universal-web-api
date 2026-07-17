from app.core.stream_monitor import StreamMonitor


class _ImageInfoElement:
    def __init__(self, result):
        self.result = result
        self.script = ""

    def run_js(self, script):
        self.script = script
        return self.result


def test_dom_image_probe_stays_enabled_for_on_signal_policy():
    monitor = StreamMonitor.__new__(StreamMonitor)
    monitor._image_extraction_enabled = True
    monitor._image_config = {
        "modalities": {
            "image": {"enabled": True, "run_policy": "on_signal"},
        }
    }
    monitor._expect_image_output = False

    assert monitor._should_probe_dom_images() is True


def test_blob_image_counts_as_signal_without_remote_prefetch_url():
    monitor = StreamMonitor.__new__(StreamMonitor)
    element = _ImageInfoElement(
        {
            "count": 1,
            "urls": [],
        }
    )

    result = monitor._extract_image_info(element)

    assert result == {"count": 1, "urls": []}
    assert "blob:" in element.script
    assert "data:image" in element.script
