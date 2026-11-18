# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300	 | Không đạt (Recall & κ thấp)	 | loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | HL-015 | judge=PASS | human=FAIL | human đúng | Reply báo hoàn 55k nhưng ledger thực tế chỉ hoàn 40k. Judge bị đánh lừa bởi văn phong lịch sự mà không đối chiếu ledger. Sửa: Tiêu chí tiền bạc không dùng Judge mà phải dùng Code Grader |
| 2 | HL-020 | judge=PASS | human=FAIL | human đúng | Reply báo hoàn 90k nhưng ledger thực tế ghi nhận 120k. Lỗi misreport nghiêm trọng bị Judge bỏ lọt |
| 3 | HL-035 | judge=PASS | human=FAIL | human đúng | Văn mẫu xin lỗi dài dòng che giấu việc báo sai số tiền (ledger ghi 40k) |
| 4 | H-042 | judge=FAIL | human=PASS | human đúng | lời reply ngắn nhưng đủ ý, judge phạt vì 'thiếu xin lỗi' trong câu |
| 1 | H-029 | judge=PASS | human=FAIL | human đúng | REPLY theo giọng ra lệnh ('không cần nhắn thêm'), judge chỉ thấy 'Dạ, vui lòng' nên đánh pass|

## Kết luận
- Tiêu chí bị loại: helpful bị loại do: 
+ Lý do kỹ thuật (dẫn ma trận nhầm lẫn): judge_helpful có ma trận nhầm lẫn {'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}, Trong 30 ca lỗi theo nhãn người (tp + fn = 30), Judge chỉ bắt được 9 ca và bỏ lọt tới 21 ca (recall chỉ đạt 30%, sai sót 70%), k =0.375 thì tỷ lệ đồng thuận chỉ nhỉnh hơn đoán bừa , vì vậy không thể dùng judge_helpful làm CI gate vì sẽ để lọt phần lớn phản hồi vô dụng
- Rủi ro còn lại: Dữ liệu calibration là dữ liệu replay công khai, trong môi trường production cần tập dữ liệu held-out mới từ người dùng thật để tránh overfitting rubric
