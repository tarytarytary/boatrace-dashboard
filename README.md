# スマホだけで設定する全国BOAT RACE一次判定ページ

このリポジトリは試験版です。**公式サイトからの実取得と解析は未検証です。** 取得失敗時には未判定として表示します。ページは公開されます。

## Android Chromeでの手順
1. GitHubで無料アカウントを作る（既存ならログイン）。
2. 新しい **Public** リポジトリを `boatrace-dashboard` の名前で作成する。
3. このZIPをスマホの「ファイル」アプリで展開する。
4. GitHubのリポジトリで **Add file → Upload files** から、展開したフォルダの中身をアップロードする。`.github/workflows/daily.yml` のような隠しフォルダをスマホでアップロードできない場合は、GitHubの **Add file → Create new file** からそのパスで新規作成し、内容を貼り付ける。GitHubのモバイル画面ではChromeの「PC版サイト」表示が便利。
5. リポジトリの **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にする。
6. **Actions → 全国一次判定と専用ページ更新 → Run workflow** で初回手動実行。
7. Actionsで緑色のチェックが出たら、**Settings → Pages → Visit site** で表示を確認する。GitHubユーザー名が `example` ならURLは `https://example.github.io/boatrace-dashboard/`。
8. Chromeのメニューから「ホーム画面に追加」で毎日ワンタップ確認。

## 注意
- GitHub Actionsの定期実行は指定時刻から遅れることがあります。日本時間7:07を設定しています。
- 公式HTML構造が変わった場合やサイトにアクセスできない場合、未判定や実行エラーになります。
- 現在の採点表は同梱の `scoring_config.json` を使用。過去に承認された換算表との一致は運用前に再確認してください。
- 初回公開前の `site/data.json` はなく、初回Actions実行後に生成されます。
