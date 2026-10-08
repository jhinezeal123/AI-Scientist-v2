"""Source URL references and import of fixed local readiness snapshots."""
import json
import re
from urllib.parse import urlsplit


def source_urls(source):
    """Read HTTP(S) references supplied explicitly or inside a source description."""
    candidates = [source.get('url'), *(source.get('urls') or []),
                  *re.findall(r'https?://[^\s<>"\x00-\x20]+', source.get('content') or '')]
    result = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        candidate = candidate.rstrip('.,;!\'')
        for opening, closing in [('(', ')'), ('[', ']'), ('{', '}')]:
            while candidate.endswith(closing) and candidate.count(closing) > candidate.count(opening):
                candidate = candidate[:-1]
        try:
            parsed = urlsplit(candidate)
            if (len(candidate) <= 2000 and parsed.scheme in {'http', 'https'} and parsed.hostname
                    and not parsed.username and not parsed.password and candidate not in result):
                result.append(candidate)
        except ValueError:
            continue
    return result


def source_has_text(content, urls):
    remainder = content
    for url in urls:
        remainder = remainder.replace(url, '')
    return bool(remainder.strip(' \t\r\n.,;!()[]{}<>\'"'))


def readiness_sources(workspace_root):
    path = workspace_root / ".workbench/readiness/pages.json"
    if not path.is_file():
        raise FileNotFoundError("T01 source snapshot is not available on this machine")
    if path.stat().st_size > 200_000:
        raise ValueError("T01 source snapshot exceeds the import limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    base = "https://www.kaggle.com/competitions/soil-grain-size-from-photos"
    paths = {"Description": "/overview", "Evaluation": "/overview/evaluation",
             "rules": "/rules", "data-description": "/data"}
    sources = []
    for page in data["pages"]:
        name = page["name"]
        if name in paths:
            content = page["content"]
            if name == "Evaluation":
                content += "\n\nT01 image formula verified 2026-10-06: EMD = sum(i=1..10, abs(F_i - prediction_i) * (log10(x_(i+1)) - log10(x_i))). Mean over soil samples; not trapezoidal integration."
            sources.append({"kind": "text", "title": "Soil competition — " + name,
                            "url": base + paths[name], "content": content})
    sources.append({"kind": "dataset", "title": "Soil dataset — T01 schema & access",
                    "url": base + "/data", "content":
                    "Verified 2026-10-06 with huynhtrungcuong. Competition ID 139732; userHasEntered=true; CSV downloads succeeded. "
                    "165 files / 395376331 bytes. Training_labels_updated.csv: 24 soil samples, sample_id + 11 cumulative target columns "
                    "0.002,0.0063,0.02,0.063,0.2,0.63,2,6.3,20,63,200. 127 training photos map uniquely to sample_id (3–8 each). "
                    "Keep every photo of one sample in the same validation fold. ppm_updated.csv has 5 cameras and phone,camera,width,height,ppm. "
                    "sample_submission.csv supplies 10 test IDs; 35 test photos. No train.csv/test.csv in the real listing. "
                    "Submission placeholders are all zero and are not valid predictions (last column must be 100). "
                    "Folders: Training-All_Photos_updated/Training-All_Photos_updated and Test_All_Photos/Test_All_Photos. "
                    "Kaggle T06 source metadata identifies mountSlug competitions/soil-grain-size-from-photos; "
                    "expected mount /kaggle/input/competitions/soil-grain-size-from-photos still requires runtime verification. "
                    "Dataset remains a reference, not stored in this project database. No training has been run."})
    return sources
