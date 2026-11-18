# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11`, run ID: `E-seeded_regression-20261118-45ca` |
| Triệu chứng | Grader `trial_pass` và `refund_amount_correct` fail (`proposal_mismatch`); ledger ghi nhận `refund_vnd = 90.000đ` trong khi nhãn kỳ vọng `120.000đ`. |
| Bước sai đầu tiên | Event #5 `kind=proposal`, payload: `{"amount_vnd": 120000}` |
| Vì sao là bước *đầu tiên* | Các bước trước đó đều đúng: Event #1 (`handoff`), #2 (`investigator`), #3 (`quote` tính đúng 150k cho hàng hỏng), #4 (`refund_history` tra đúng lịch sử đã hoàn 30k). Đến Event #5, agent tự ý trừ trước 30k (150k - 30k = 120k) đưa vào proposal, sau đó host của hệ thống lại trừ tiếp 30k nữa khiến ledger bị khấu trừ 2 lần (chỉ còn 90k). |
| Failure mode | `FM-05: pre_deducted — tự trừ tiền đã hoàn rồi mới gọi host (khấu trừ 2 lần)` |
| Đối chứng | Trên shape `fixed`, agent không tự ý trừ trước mà gửi nguyên proposal 150k tới host; host trừ 30k lịch sử và ghi nhận chuẩn xác 120k vào ledger (`ledger=120000`, `label=120000` -> PASS). |
| Regression test | `test_wrong_amount_in_ledger` (Grader `RefundAmountCorrect`); phát hiện lỗi trên `seeded_regression` (`value=False` do 90k != 120k) và pass trên `fixed` (`value=True`). |
| Chưa chắc chắn | Trace chỉ ghi nhận giao dịch trên SQLite ledger nội bộ, không chứng minh được biến động số dư tài khoản ngân hàng thực tế của khách hàng ngoài đời. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
