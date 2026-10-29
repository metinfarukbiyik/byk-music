"""Bir önceki sürümden bu yana yapılan commit'lerden Markdown sürüm notu üretir.

  python packaging/release_notes.py <sürüm> > release-notes.md

Her commit'in ilk satırı başlık, gövdesindeki "- " ile başlayan satırlar madde olur.
"Belgeler:" ile başlayan commit'ler atlanır.
"""
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def main(version: str) -> str:
    previous = git("describe", "--tags", "--abbrev=0")
    rng = f"{previous}..HEAD" if previous else "HEAD"
    log = git("log", rng, "--no-merges", "--format=%s%x1f%b%x1e")

    sections = []
    for entry in filter(None, (e.strip() for e in log.split("\x1e"))):
        subject, _, body = entry.partition("\x1f")
        if subject.strip().startswith("Belgeler:"):
            continue  # yalnızca belge değişiklikleri sürüm notuna eklenmez
        bullets, text = [], []
        for line in body.splitlines():
            line = line.rstrip()
            if not line.strip() or line.lower().startswith("co-authored-by"):
                continue
            if line.lstrip().startswith(("- ", "* ")):
                bullets.append("- " + line.lstrip()[2:].strip())
            elif bullets and line.startswith("  "):
                bullets[-1] += " " + line.strip()  # çok satırlı madde
            else:
                text.append(line.strip())
        part = [f"### {subject.strip()}"]
        if text:
            part.append(" ".join(text))
        part.extend(bullets)
        sections.append("\n".join(part))

    notes = [f"## BYK Music v{version.lstrip('v')}", ""]
    notes.append("\n\n".join(sections) if sections else "Küçük iyileştirmeler ve hata düzeltmeleri.")
    notes += ["", "---",
              "**İndirme:** Windows için `BYKMusic-Windows-Setup.exe`, macOS için `BYKMusic-macOS.dmg`. "
              "Kurulu uygulamalar bu sürümü otomatik olarak alır."]
    return "\n".join(notes)


if __name__ == "__main__":
    print(main(sys.argv[1] if len(sys.argv) > 1 else "0.0.0"))
