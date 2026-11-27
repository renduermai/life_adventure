"""Explicit media maintenance only; never scheduled or run during app startup."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import load_settings
from app.core.database import Database
from app.modules.shining_memories.shared.images import MediaError
from app.modules.shining_memories.shared.storage import SupabaseStorage
from app.modules.shining_memories.shared.service import cleanup
from app.modules.shining_memories.shared.backup import backup_media, open_backup, restore_media
# Register identity FK metadata without creating tables.
from app.modules.identity import models as _identity  # noqa: F401


def main():
    parser = argparse.ArgumentParser(description='Private cloud media backup and maintenance')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-bucket')
    sub.add_parser('check-storage')
    sub.add_parser('cleanup')
    key = sub.add_parser('keygen')
    key.add_argument('--out', required=True)
    backup = sub.add_parser('backup')
    backup.add_argument('--destination')
    verify = sub.add_parser('verify')
    verify.add_argument('archive')
    restore = sub.add_parser('restore')
    restore.add_argument('archive')
    restore.add_argument('--bucket', required=True)
    restore.add_argument('--create-bucket', action='store_true')
    args = parser.parse_args()
    database = None
    try:
        if args.command == 'keygen':
            target = Path(args.out).resolve()
            from app.core.config import ROOT
            if target.is_relative_to(ROOT.resolve()):
                raise MediaError('key_location', '密钥文件请保存在项目外，并与备份分开保管')
            with target.open('xb') as file:
                os.chmod(target, 0o600)
                file.write(base64.urlsafe_b64encode(os.urandom(32)))
            print('Key file created; key content is not printed. Protect with account ACL/encrypted storage.')
            return 0
        settings = load_settings()
        factory = lambda bucket=None: SupabaseStorage(settings, bucket)
        if args.command in ('init-bucket', 'check-storage'):
            factory().ensure_private(create=args.command == 'init-bucket')
            result = {'private_bucket_verified': True}
        elif args.command == 'verify':
            with open_backup(args.archive, settings.memory_backup_key) as (_, manifest):
                result = {'verified': True, 'images': len(manifest['assets'])}
        elif args.command == 'restore':
            if args.bucket == settings.supabase_storage_bucket:
                raise MediaError('restore_target', '禁止恢复到当前生产Bucket，请指定独立测试Bucket')
            result = restore_media(args.archive, settings.memory_backup_key,
                factory(args.bucket), create_bucket=args.create_bucket)
        else:
            database = Database(settings)
            if database.sessions is None:
                raise MediaError('database_config', '请先配置数据库', 503)
            if args.command == 'backup':
                result = backup_media(database, settings, factory, args.destination)
            else:
                result = cleanup(database, factory)
        print(json.dumps(result, ensure_ascii=True))
        return 1 if result.get('failed') else 0
    except MediaError as error:
        print(f'{error.code}: {error.message}', file=sys.stderr)
        return 1
    except Exception as error:
        # Do not echo SQL parameters, file contents, URLs or credentials.
        print(f'Operation failed ({type(error).__name__}); no credentials printed.', file=sys.stderr)
        return 1
    finally:
        if database:
            database.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
