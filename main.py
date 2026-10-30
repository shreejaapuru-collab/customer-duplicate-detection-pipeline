"""CLI entry point:  python main.py [--input data/sample/customers.csv] [--output-dir outputs]"""
import argparse
import sys

from src.duplicate_detection import MatchConfig
from src.ingestion import IngestionError
from src.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer duplicate detection pipeline")
    parser.add_argument("--input", default="data/sample/customers.csv")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--auto-merge-threshold", type=float, default=MatchConfig.auto_merge_threshold)
    args = parser.parse_args()

    cfg = MatchConfig(auto_merge_threshold=args.auto_merge_threshold)
    try:
        run_pipeline(args.input, args.output_dir, args.log_dir, cfg)
    except IngestionError:
        return 2  # already logged; file rejected
    return 0


if __name__ == "__main__":
    sys.exit(main())
