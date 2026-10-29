# Runbook — Triển khai và vận hành Match Performance trên Oracle Cloud (miễn phí)

Tài liệu thao tác cho người triển khai/vận hành. Thiết kế: [docs/detailed-design-cloud-deployment.md](../docs/detailed-design-cloud-deployment.md).
Các lệnh có dấu `$` chạy trên **máy chủ Ubuntu** (qua SSH); dấu `PS>` chạy trên **máy Windows của bạn**.

> ⚠ **Cổng pháp lý G0 (§3 thiết kế):** chỉ mở cho nhóm kín (đăng ký cần admin duyệt — mặc định). Đừng quảng bá công khai
> khi chưa có giấy phép dữ liệu / API có giấy phép.

---

## 1. Chuẩn bị (một lần, ~30 phút)

| Việc | Cách làm |
| --- | --- |
| Tài khoản Oracle Cloud | Đăng ký tại oracle.com/cloud/free (cần thẻ để xác minh, không trừ tiền ở gói Always Free). Chọn **Home Region** gần bạn (vd Singapore, Tokyo) — không đổi được về sau |
| Khoá SSH | `PS> ssh-keygen -t ed25519 -f $HOME\.ssh\oracle_matchperf` (Enter 2 lần) — dùng file `.pub` khi tạo máy |
| Tên miền DuckDNS | Vào duckdns.org → đăng nhập → tạo subdomain (vd `tenban`) → ghi lại **token** |
| Email gửi thư (tuỳ chọn) | Tạo tài khoản dịch vụ SMTP có gói miễn phí (vd Brevo) → xác minh một địa chỉ gửi → lấy SMTP host/port/user/key. Không có cũng chạy được: thư in ra log, admin duyệt tay |

## 2. Tạo máy ảo (P0)

1. Oracle Console → **Compute → Instances → Create instance**.
2. Image: **Canonical Ubuntu 24.04** (bản aarch64). Shape: **Ampere → VM.Standard.A1.Flex**, **2 OCPU, 12 GB RAM** (đúng hạn mức Always Free 2026 — đừng chọn cao hơn).
3. Networking: VCN mặc định, **Assign a public IPv4 address**. SSH key: dán nội dung file `oracle_matchperf.pub`.
4. Boot volume: 50 GB. Bấm **Create**. Nếu báo *Out of capacity* ⇒ thử lại sau vài giờ hoặc đổi Availability Domain.
5. Mở cổng web: VCN → Subnet → **Security List** → *Add Ingress Rules*: nguồn `0.0.0.0/0`, TCP, cổng `80` và `443`.
6. Ghi lại **Public IP**. Đăng nhập thử: `PS> ssh -i $HOME\.ssh\oracle_matchperf ubuntu@<PUBLIC_IP>`

## 3. Cài đặt máy chủ

```bash
$ sudo apt update && sudo apt -y upgrade && sudo apt -y install git unattended-upgrades sqlite3
$ curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker ubuntu && exit     # đăng nhập lại để có quyền docker
# Ubuntu trên Oracle chặn cổng bằng iptables — mở 80/443:
$ sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
$ sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
$ sudo netfilter-persistent save
# Swap 2 GB (đệm cho Chromium)
$ sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
$ echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
# SSH chỉ bằng khoá (mặc định Oracle đã tắt mật khẩu; kiểm tra lại):
$ grep -E '^(PasswordAuthentication|PermitRootLogin)' /etc/ssh/sshd_config*
```

**DuckDNS trỏ về máy** (cập nhật IP mỗi 5 phút):

```bash
$ mkdir -p ~/duckdns && echo 'echo url="https://www.duckdns.org/update?domains=TENBAN&token=TOKEN&ip=" | curl -k -o ~/duckdns/duck.log -K -' > ~/duckdns/duck.sh
$ chmod 700 ~/duckdns/duck.sh && (crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
$ ~/duckdns/duck.sh && cat ~/duckdns/duck.log        # phải in OK
```

## 4. Đưa mã nguồn lên máy

Cách A — từ máy Windows (không cần GitHub):

```powershell
PS> cd "C:\Automation Football Dashboard"
PS> git archive --format=tar.gz -o $env:TEMP\matchperf.tar.gz HEAD
PS> scp -i $HOME\.ssh\oracle_matchperf $env:TEMP\matchperf.tar.gz ubuntu@<PUBLIC_IP>:~/
```
```bash
$ mkdir -p ~/app && tar -xzf ~/matchperf.tar.gz -C ~/app
```
(`git archive` chỉ lấy nội dung **đã commit** — commit trước khi gửi.)

Cách B — GitHub repo private: `$ git clone git@github.com:<bạn>/<repo>.git ~/app` (cần deploy key).

## 5. Kiểm tra P0 — Flashscore có chặn IP máy chủ không (BẮT BUỘC trước khi làm tiếp)

```bash
$ cd ~/app/deploy && cp .env.example .env && nano .env      # tạm thời chỉ cần APP_DOMAIN / APP_BASE_URL
$ docker compose build
$ for u in \
  "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n" \
  "https://www.flashscore.com/match/football/malaga-25tIqYiJ/villarreal-lUatW5jE/?mid=GGiPsLP1" \
  "https://www.flashscore.com/match/football/altglienicke-EP8ggpyE/wolfsburg-nwkTahLL/?mid=d8pxv90m" \
  "https://www.flashscore.com/match/football/coventry-GOvB22xg/newcastle-utd-p6ahwuwJ/?mid=tW4rOkzg" ; do
    docker compose run --rm worker python -m cloud.canary "$u"; done
```

- Tất cả in `✓ canary …` ⇒ **go**. Ghi lại thời gian mỗi trận (bình thường 25–60 s).
- Có `E_BLOCKED` / `E_TIMEOUT` lặp lại ⇒ **no-go**: dừng ở đây, báo lại để chọn hạ tầng / nguồn dữ liệu khác.

## 6. Cấu hình và khởi chạy

```bash
$ cd ~/app/deploy && nano .env          # điền APP_DOMAIN, APP_BASE_URL=https://<APP_DOMAIN>, SMTP_*, ADMIN_EMAIL
$ chmod 600 .env
$ docker compose up -d --build
$ docker compose ps                     # 3 dịch vụ: caddy, web, worker — đều "running"
$ docker compose logs -f caddy          # chờ dòng "certificate obtained successfully" (HTTPS sẵn sàng)
$ docker compose exec web python -m cloud.admin create-admin --email ban@example.com     # nhập mật khẩu ≥ 10 ký tự
```

Mở `https://<APP_DOMAIN>` → đăng nhập bằng tài khoản admin → dán thử link Johor DT → mở báo cáo → Export PDF.

## 7. Tác vụ định kỳ (cron trên máy chủ)

```bash
$ crontab -e      # thêm 2 dòng:
0 3 * * *  cd ~/app/deploy && docker compose exec -T web python -m cloud.backup >> ~/backup.log 2>&1
30 2 * * * cd ~/app/deploy && docker compose exec -T worker python -m cloud.canary >> ~/canary.log 2>&1
```

- **Sao lưu ngoài máy (khuyến nghị):** Oracle Console → Storage → Buckets → *Create bucket* (vd `matchperf-backup`) →
  *Pre-Authenticated Requests* → loại **Permit object writes**, hạn 1 năm → dán URL vào `BACKUP_PAR_URL` trong `.env` →
  `docker compose up -d`. Kiểm tra: `docker compose exec web python -m cloud.backup` in `→ Object Storage`.
- **Giám sát:** tạo monitor HTTP(S) miễn phí trên UptimeRobot tới `https://<APP_DOMAIN>/api/health` (5 phút). Trang trả
  503 khi worker im lặng > 60 s.

## 8. Vận hành hằng ngày

| Việc | Lệnh / thao tác |
| --- | --- |
| Duyệt tài khoản mới | Đăng nhập → **Admin** → *Approve* (email chưa xác minh thì nút bị khoá) |
| Mời người dùng | Admin → *Invite someone* (họ nhận link đặt mật khẩu) |
| Đổi chế độ đăng ký | Admin → *Sign-up*: Open with approval ★ / Open / Invitation only |
| Crawl bị tạm dừng (Flashscore chặn) | Admin → *Resume crawling*, hoặc `docker compose exec web python -m cloud.admin reset-breaker` |
| Xem log | `docker compose logs --tail 200 web` · `… worker` · `… caddy` |
| Thư bị in ra log (chưa cấu hình SMTP) | `docker compose logs web | grep mail:console` — chứa link xác minh/đặt lại |
| Cập nhật phiên bản | Gửi mã mới (mục 4) ⇒ `docker compose up -d --build` |
| Khôi phục từ bản sao lưu | `docker compose stop web worker` ⇒ `docker compose run --rm web python -m cloud.backup --restore /data/backups/<file>.db.gz` ⇒ `docker compose start web worker` |
| Khoá tài khoản khẩn cấp | `docker compose exec web python -m cloud.admin set-status --email x@y.z --status disabled` |
| Quên mật khẩu admin | `docker compose exec web python -m cloud.admin create-admin --email <email admin>` (đặt lại mật khẩu) |

## 9. Sự cố thường gặp

| Hiện tượng | Nguyên nhân / xử lý |
| --- | --- |
| Không mở được trang (timeout) | Chưa mở cổng 80/443 ở Security List **và** iptables (mục 2.5, 3) |
| Caddy báo lỗi lấy chứng chỉ | DuckDNS chưa trỏ đúng IP (`cat ~/duckdns/duck.log`, `ping <APP_DOMAIN>`) |
| `/api/health` trả 503 | Worker dừng: `docker compose logs worker`; `docker compose restart worker` |
| Mọi job lỗi `E_BLOCKED` | Flashscore chặn IP ⇒ hệ thống tự tạm dừng 30 phút; lặp lại ⇒ cần đổi hạ tầng / nguồn dữ liệu |
| Oracle báo máy bị thu hồi / vô hiệu hoá | Tạo máy mới (mục 2–6), khôi phục bản sao lưu từ bucket |
| Hết RAM | `docker stats`; giảm `FS_PARALLEL` của worker trong `docker-compose.yml` xuống `1` |
