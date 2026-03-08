import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_CSV_DIR = str((Path(__file__).resolve().parent / "code_neo4j_csv"))
DEFAULT_IMPORT_DIR = r"E:\neo4j\import"
DEFAULT_DATA_DIR = r"E:\neo4j\data"
DEFAULT_LOGS_DIR = r"E:\neo4j\logs"


class CommandError(RuntimeError):
    pass


def run(cmd, *, check=True, capture_output=False, text=True):
    p = subprocess.run(
        cmd,
        check=False,
        capture_output=capture_output,
        text=text,
    )
    if check and p.returncode != 0:
        stdout = p.stdout or ""
        stderr = p.stderr or ""
        raise CommandError(
            f"命令执行失败: {cmd}\nexit_code={p.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return p


def ensure_docker():
    if shutil.which("docker") is None:
        raise CommandError("找不到 docker 命令。请安装/配置 Docker，并确保 docker 可用。")


def image_exists(image):
    try:
        images = set(list_local_images())
    except CommandError:
        return False
    return image in images


def list_local_images():
    p = run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
        check=True,
        capture_output=True,
    )
    lines = [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
    return lines


def resolve_image(image: str) -> str:
    if "/" in image:
        name_part = image.rsplit("/", 1)[-1]
    else:
        name_part = image

    has_tag = ":" in name_part
    if has_tag:
        return image

    candidates = list_local_images()
    matches = [c for c in candidates if c.startswith(image + ":")]
    if not matches:
        return image

    if image + ":latest" in matches:
        return image + ":latest"

    def score(tagged: str):
        tag = tagged.split(":", 1)[1]
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", tag)
        if m:
            return (3, int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"^(\d+)\.(\d+)$", tag)
        if m:
            return (2, int(m.group(1)), int(m.group(2)), 0)
        m = re.match(r"^(\d+)$", tag)
        if m:
            return (1, int(m.group(1)), 0, 0)
        return (0, 0, 0, 0)

    matches.sort(key=score, reverse=True)
    return matches[0]


def container_exists(name):
    p = run(["docker", "container", "inspect", name], check=False, capture_output=True)
    return p.returncode == 0


def stop_and_remove_container(name):
    if container_exists(name):
        run(["docker", "rm", "-f", name], check=True)


def build_import_args(csv_dir):
    csv_dir = Path(csv_dir)
    if not csv_dir.exists():
        raise CommandError(f"CSV 目录不存在: {csv_dir}")

    headers = sorted(csv_dir.glob("*_header.csv"))
    bases = []
    for header_path in headers:
        base = header_path.name[: -len("_header.csv")]
        data_path = csv_dir / f"{base}_data.csv"
        if data_path.exists():
            bases.append(base)

    node_bases = [b for b in bases if b.startswith("nodes_")]
    rel_bases = [b for b in bases if b.startswith("edges_")]

    if not node_bases:
        raise CommandError(f"未找到可导入的 nodes_*_header.csv + nodes_*_data.csv 文件对: {csv_dir}")
    if not rel_bases:
        raise CommandError(f"未找到可导入的 edges_*_header.csv + edges_*_data.csv 文件对: {csv_dir}")

    args = []
    for base in node_bases:
        args.append(
            f"--nodes=/var/lib/neo4j/import/{base}_header.csv,/var/lib/neo4j/import/{base}_data.csv"
        )
    for base in rel_bases:
        args.append(
            f"--relationships=/var/lib/neo4j/import/{base}_header.csv,/var/lib/neo4j/import/{base}_data.csv"
        )
    return args, node_bases, rel_bases


def to_docker_mount_path(host_path: Path) -> str:
    p = host_path.resolve()
    if os.name == "nt":
        drive = p.drive.rstrip(":").upper()
        rest = p.as_posix().split(":", 1)[1].lstrip("/")
        return f"{drive}:/{rest}"
    return str(p)


def copy_csv_files(src_dir: Path, dst_dir: Path) -> int:
    src_dir = src_dir.resolve()
    dst_dir = dst_dir.resolve()
    if not src_dir.exists():
        raise CommandError(f"CSV 源目录不存在: {src_dir}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in src_dir.glob("*.csv"):
        shutil.copy2(p, dst_dir / p.name)
        count += 1
    if count == 0:
        raise CommandError(f"在源目录未找到任何 .csv 文件: {src_dir}")
    return count


def patch_node_headers(import_dir: Path) -> int:
    import_dir = import_dir.resolve()
    patched = 0
    for header_path in import_dir.glob("nodes_*_header.csv"):
        text = header_path.read_text(encoding="utf-8-sig", errors="strict")
        new_text = re.sub(r"^\ufeff?:ID,", "id:ID,", text, count=1)
        if new_text != text:
            header_path.write_text(new_text, encoding="utf-8", newline="")
            patched += 1
    return patched


def wait_for_neo4j(container_name, password, timeout_s):
    start = time.time()
    last_err = None
    while time.time() - start < timeout_s:
        p = run(
            [
                "docker",
                "exec",
                container_name,
                "cypher-shell",
                "-u",
                "neo4j",
                "-p",
                password,
                "RETURN 1;",
            ],
            check=False,
            capture_output=True,
        )
        if p.returncode == 0:
            return
        last_err = (p.stdout or "") + "\n" + (p.stderr or "")
        time.sleep(2)
    raise CommandError(f"等待 Neo4j 就绪超时({timeout_s}s)。最后一次错误输出:\n{last_err}")


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default=DEFAULT_CSV_DIR)
    parser.add_argument("--import-dir", default=DEFAULT_IMPORT_DIR)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--logs-dir", default=DEFAULT_LOGS_DIR)
    parser.add_argument("--image", default="neo4j")
    parser.add_argument("--database", default="neo4j")
    parser.add_argument("--container-name", default="CodeScope_neo4j")
    parser.add_argument("--password", default="neo4j@1234")
    parser.add_argument("--http-port", type=int, default=7474)
    parser.add_argument("--bolt-port", type=int, default=7687)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--no-stop", action="store_true")
    parser.add_argument("--no-overwrite", action="store_true")
    parser.add_argument("--no-copy", action="store_true")
    parser.add_argument("--no-patch-headers", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=120)
    parser.add_argument("--pull-if-missing", action="store_true")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    ensure_docker()

    resolved_image = resolve_image(args.image)
    if args.pull_if_missing:
        if ":" in resolved_image:
            pull_target = resolved_image
        else:
            pull_target = args.image
        run(["docker", "pull", pull_target], check=False)
        resolved_image = resolve_image(args.image)

    csv_dir = Path(args.csv_dir)
    import_dir = Path(args.import_dir)
    data_dir = Path(args.data_dir)
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_copy:
        copied = copy_csv_files(csv_dir, import_dir)
        print(f"已复制 {copied} 个 CSV 文件到: {import_dir}")

    if not args.no_patch_headers:
        patched = patch_node_headers(import_dir)
        print(f"已修正 {patched} 个 nodes_*_header.csv 的 :ID -> id:ID")

    import_args, node_bases, rel_bases = build_import_args(import_dir)

    if not args.no_stop:
        run(["docker", "stop", args.container_name], check=False)

    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{to_docker_mount_path(data_dir)}:/data",
        "-v",
        f"{to_docker_mount_path(import_dir)}:/var/lib/neo4j/import",
        "-v",
        f"{to_docker_mount_path(logs_dir)}:/logs",
        resolved_image,
        "neo4j-admin",
        "database",
        "import",
        "full",
        args.database,
    ]
    if not args.no_overwrite:
        cmd.append("--overwrite-destination=true")
    cmd += import_args

    print("开始执行 neo4j-admin database import ...")
    print("image:", resolved_image)
    print("nodes:", len(node_bases), "relationships:", len(rel_bases))
    run(cmd, check=True)
    print("导入完成。")
    try:
        latest = max(logs_dir.glob("neo4j-admin-import-*.log"), key=lambda p: p.stat().st_mtime)
        print(f"导入日志: {latest}")
    except ValueError:
        pass

    if args.no_start:
        return
    run(["docker", "start", args.container_name], check=False)
    print("已尝试启动 Neo4j 容器。")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except CommandError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
