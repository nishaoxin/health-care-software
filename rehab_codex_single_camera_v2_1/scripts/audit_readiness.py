"""Inventory all registered action content and prepare empty acceptance inputs.

No camera, model, network, raw recording decode or personal database access.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.readiness import content_inventory, check_sample_manifest, SAMPLE_COLUMNS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing files are not overwritten')
    parser.add_argument('--sample-manifest', type=Path)
    parser.add_argument('--verify-files', action='store_true', help='Read explicitly listed recording files and compare SHA256')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('输出目录非空，请选择新目录')
    output.mkdir(parents=True, exist_ok=True)
    audit = content_inventory()
    (output/'action-content.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    columns = ['exercise_id', 'exercise_label', 'joint', 'side', 'view', 'primary_metric', 'measurement_contract',
               'target_direction', 'baseline_required', 'content_fields_complete', 'start', 'move', 'return_step',
               'camera', 'count', 'boundary', 'expert_content_review', 'human_accuracy']
    with (output/'action-content.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(audit['rows'])
    with (output/'sample-manifest-template.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        csv.writer(stream).writerow(SAMPLE_COLUMNS)
    samples = check_sample_manifest(args.sample_manifest, verify_files=args.verify_files) if args.sample_manifest else {
        'ready': False, 'rows': 0, 'status': 'NOT_PROVIDED', 'accuracy_validated': False}
    (output/'sample-readiness.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    summary = {k: audit[k] for k in ('action_count', 'body_part_count', 'side_entries', 'image_slots', 'present_images', 'content_structure_errors')}
    summary['sample_inputs'] = samples
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if audit['content_structure_errors'] or args.sample_manifest and not samples['ready'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
