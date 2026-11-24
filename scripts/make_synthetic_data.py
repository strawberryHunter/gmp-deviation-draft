"""Create synthetic deviation history and intake forms.

All sites, products, batches, equipment and people are fictional.
    python scripts/make_synthetic_data.py
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
rng = random.Random(11)

SITES = ["Plant A", "Plant B"]
EQUIP = {
    "BR-2001": ("Bioreactor 2,000 L", "process_parameter"),
    "CF-101": ("Depth filtration skid", "equipment"),
    "CHR-03": ("Protein A chromatography skid", "process_parameter"),
    "UF-02": ("UF/DF skid", "equipment"),
    "FIL-L2": ("Fill line 2 (isolator)", "environmental_monitoring"),
    "LYO-01": ("Lyophilizer 1", "utilities"),
    "WFI-LOOP": ("WFI distribution loop", "utilities"),
    "BSC-14": ("Biosafety cabinet 14", "environmental_monitoring"),
}
EXTRA_CATS = ["documentation", "material", "personnel"]


def make_history(n: int = 48, end: date = date(2026, 11, 20)) -> list[dict]:
    rows = []
    for i in range(n):
        eq = rng.choice(list(EQUIP))
        cat = EQUIP[eq][1] if rng.random() < 0.7 else rng.choice(EXTRA_CATS)
        d = end - timedelta(days=rng.randint(5, 540))
        rows.append({
            "dev_id": f"DEV-{d.year}-{1000 + i}",
            "opened": d.isoformat(),
            "site": rng.choice(SITES),
            "equipment_id": eq,
            "category": cat,
            "final_class": rng.choices(["minor", "major", "critical"], [0.7, 0.27, 0.03])[0],
            "root_cause": rng.choice(["human error", "equipment wear", "procedure gap", "supplier material", "undetermined"]),
            "synthetic": True,
        })
    # make CHR-03 / process_parameter a recurring problem in the last year
    for k in range(3):
        d = end - timedelta(days=30 + 70 * k)
        rows.append({"dev_id": f"DEV-{d.year}-{1100 + k}", "opened": d.isoformat(), "site": "Plant A",
                     "equipment_id": "CHR-03", "category": "process_parameter", "final_class": "major",
                     "root_cause": "procedure gap", "synthetic": True})
    return sorted(rows, key=lambda r: r["opened"])


INTAKE = [
    {
        "id": "DEV-2026-2201",
        "title": "Protein A 크로마토그래피 용출 pH 상한 이탈",
        "site": "Plant A", "area": "Downstream Suite 3", "product": "SYN-mAb-07 drug substance",
        "batch": "DS-26-0412", "equipment_id": "CHR-03", "category": "process_parameter",
        "detected_at": "2026-11-21T14:20", "detected_by": "공정 운전원 (2교대)",
        "process_step": "Protein A capture - elution",
        "description": "용출 단계 pH가 3.62로 기록됨 (허용 범위 3.40-3.60). 이탈 시간 약 6분. 용출 완충액 lot BUF-5531 사용.",
        "immediate_actions": "공정 일시 중단, 용출 분획 격리 보관(2-8°C), 교대 감독자 및 QA 통보 (15:05).",
        "parameters": [{"name": "Elution pH", "spec": "3.40-3.60", "actual": "3.62", "duration": "6 min"}],
        "cpp_excursion": True, "spec_oos": False, "other_batches_possibly_affected": True,
        "sterility_assurance_impacted": False, "released_product_affected": False, "data_integrity_concern": False,
    },
    {
        "id": "DEV-2026-2202",
        "title": "충전 라인 2 아이솔레이터 장갑 리크 테스트 부적합",
        "site": "Plant B", "area": "Aseptic Filling", "product": "SYN-mAb-03 drug product (PFS)",
        "batch": "DP-26-1180", "equipment_id": "FIL-L2", "category": "environmental_monitoring",
        "detected_at": "2026-11-22T06:45", "detected_by": "무균 충전 작업자",
        "process_step": "Pre-use glove integrity test",
        "description": "충전 전 장갑 무결성 시험에서 포트 4번 장갑 부적합. 직전 배치(DP-26-1179) 충전 종료 후 시험은 적합이었음.",
        "immediate_actions": "충전 착수 보류, 장갑 교체 및 재시험 적합, 직전 배치 EM 데이터 검토 요청.",
        "parameters": [{"name": "Glove leak test", "spec": "Pass", "actual": "Fail (port 4)"}],
        "cpp_excursion": False, "spec_oos": False, "other_batches_possibly_affected": True,
        "sterility_assurance_impacted": True, "released_product_affected": False, "data_integrity_concern": False,
    },
    {
        "id": "DEV-2026-2203",
        "title": "배치 기록서 서명 누락 (원료 칭량 단계)",
        "site": "Plant A", "area": "Dispensing", "product": "SYN-mAb-07 drug substance",
        "batch": "DS-26-0415", "equipment_id": "", "category": "documentation",
        "detected_at": "2026-11-23T10:10", "detected_by": "QA 기록 검토자",
        "process_step": "Raw material dispensing",
        "description": "배지 성분 칭량 단계에서 확인자(2nd person) 서명 누락. 칭량 저울 출력지는 첨부되어 있음.",
        "immediate_actions": "작업자 및 확인자 인터뷰 예정, 저울 출력지와 기록 대조.",
        "cpp_excursion": False, "spec_oos": False, "other_batches_possibly_affected": False,
        "sterility_assurance_impacted": False, "released_product_affected": False, "data_integrity_concern": False,
    },
    {
        "id": "DEV-2026-2204",
        "title": "WFI 루프 TOC 경고 수준 초과",
        "site": "Plant B", "area": "Utilities", "product": "N/A (utility)",
        "batch": "N/A", "equipment_id": "WFI-LOOP", "category": "utilities",
        "detected_at": "2026-11-23T03:30",
        "process_step": "Routine WFI monitoring",
        "description": "사용 지점 POU-07 TOC 412 ppb (경고 기준 400 ppb, 조치 기준 500 ppb).",
        "immediate_actions": "POU-07 사용 중지 표시, 재샘플링 요청.",
        "parameters": [{"name": "TOC (POU-07)", "spec": "Alert 400 / Action 500 ppb", "actual": "412 ppb"}],
        "cpp_excursion": False, "spec_oos": False, "other_batches_possibly_affected": False,
        "sterility_assurance_impacted": False, "released_product_affected": False, "data_integrity_concern": False,
    },
]


def main() -> None:
    hist = make_history()
    out = ROOT / "data/synthetic/history.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(hist[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(hist)
    print(f"history: {len(hist)} rows -> {out}")
    for form in INTAKE:
        p = ROOT / "data/synthetic/intake" / f"{form['id']}.yaml"
        p.write_text(yaml.safe_dump({"synthetic": True, **form}, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"intake: {p.name}")


if __name__ == "__main__":
    main()
