"""Visible account ID parsing accepts typography, never substring matches."""
import asyncio,unittest
from unittest.mock import AsyncMock,MagicMock,patch
import collect_batch as batch

class IdentityTests(unittest.TestCase):
    def test_config_normalizes_fullwidth_digits(self):
        import tempfile,json
        from pathlib import Path
        import local_config
        with tempfile.TemporaryDirectory() as temp,patch.object(local_config,'ROOT',Path(temp)):
            local_config.save_config('测试账户','１２３４５')
            self.assertEqual(json.loads((Path(temp)/'config.local.json').read_text(encoding='utf-8'))['account_id'],'12345')
            with self.assertRaises(ValueError):local_config.save_config(None,'12345')
    def test_equivalent_formats(self):
        for text in ('账户ID:12345','账户ID：12345','账户 ID : 12345','账户ID:\n12345','账号ID： 12345','账户ＩＤ：１２３４５','账户ID:\u200b12345'):
            self.assertEqual(batch.account_ids(text),{'12345'})
    def test_no_substring_or_unlabelled_number(self):
        self.assertEqual(batch.account_ids('订单12345 商品ID:12345'),set())
        self.assertEqual(batch.account_ids('账户ID:123456'),{'123456'})
    def test_mismatched_and_ambiguous_accounts_rejected(self):
        page=MagicMock();text=page.locator.return_value.inner_text=AsyncMock()
        with patch.object(batch,'ACCOUNT_ID','12345'):
            for value in ('账户ID:123456','账户ID:12345 账号ID:999'):
                text.return_value=value
                with self.assertRaises(RuntimeError):asyncio.run(batch.verify_account(page))
            text.return_value='账户ID： 12345';asyncio.run(batch.verify_account(page))
    def test_loading_retried_and_missing_rejected(self):
        page=MagicMock();text=page.locator.return_value.inner_text=AsyncMock(side_effect=['加载中','账户ID：12345'])
        with patch.object(batch,'ACCOUNT_ID','12345'),patch.object(batch.asyncio,'sleep',new_callable=AsyncMock):asyncio.run(batch.verify_account(page))
        text.side_effect=None;text.return_value='尚未登录'
        with patch.object(batch.asyncio,'sleep',new_callable=AsyncMock),self.assertRaisesRegex(RuntimeError,'无法读取页面账户ID'):asyncio.run(batch.verify_account(page))

if __name__=='__main__':unittest.main()
