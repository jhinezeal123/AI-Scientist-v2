# Research: giảm lỗi code/notebook cho agent

Ngày khảo sát: **2026-10-07**. Đã đọc source AI Scientist v2 trong checkout và tài liệu
chính thức của các công cụ dưới đây. Chưa cài SDK hoặc thay engine training của MVP0.

## 1. Kết luận

Có sản phẩm đáp ứng hướng “agent điền cấu hình/template”:

- **PyTorch Lightning**: phù hợp làm nền cho template training của model PyTorch tự viết.
- **Axolotl** hoặc **LlamaFactory**: gần nhất với việc điền YAML để finetune LLM/VLM.
- **Papermill**: chạy notebook có tham số, phù hợp khi đã có notebook mẫu đúng.

Đánh giá cho project này: bước có tác dụng trực tiếp nhất là **giữ notebook wrapper do app
tạo, thêm lớp xác minh dữ liệu/đường dẫn, rồi cung cấp template theo loại tác vụ**.
Framework training giảm phần vòng lặp train mà agent phải viết. Lớp dữ liệu mới là nơi
xử lý mount Kaggle, tên CSV, cột label, ghép ảnh với sample và split theo nhóm.
Không có bằng chứng từ tài liệu đã khảo sát rằng những công cụ này tự hiểu schema riêng
của competition Soil hoặc tự sửa mount sai trong code agent tạo.

## 2. AI Scientist v2 gốc xử lý ra sao?

README mô tả v2 bỏ sự phụ thuộc vào template do con người viết để mở rộng phạm vi khám phá.
Tác giả cũng thừa nhận cách dựa trên template của v1 có thể đạt tỉ lệ thành công cao hơn
khi nhiệm vụ rõ ràng. [README chính thức](https://github.com/SakanaAI/AI-Scientist-v2)

Đường chạy trong source hiện có:

```text
Idea + mô tả môi trường/dữ liệu
    → LLM sinh kế hoạch + script Python
    → tách code, kiểm cú pháp, format
    → Interpreter chạy script trong process riêng
    → thu stdout/stderr/exception/traceback
    → node lỗi → prompt debug với code và lỗi trước đó
    → script sửa → thực thi tiếp trong ngân sách tìm kiếm
```

| Trách nhiệm | Source đã đọc | Cách xử lý |
|---|---|---|
| Sinh script ban đầu | [`parallel_agent.py:453`](D:/Documents/AI-Scientist-v2/ai_scientist/treesearch/parallel_agent.py:453) | `_draft` yêu cầu code end-to-end, đưa idea, môi trường và hướng dẫn vào prompt. |
| Tách code | [`response.py:55`](D:/Documents/AI-Scientist-v2/ai_scientist/treesearch/utils/response.py:55) | `extract_code` lấy code block, có fallback; loại code không parse được; format bằng Black. |
| Thử lại khi output sai dạng | [`parallel_agent.py:658`](D:/Documents/AI-Scientist-v2/ai_scientist/treesearch/parallel_agent.py:658) | `plan_and_code_query(..., retries=3)` phản hồi lỗi tách plan/code cho LLM. Đây là retry format, chưa chứng minh code chạy đúng. |
| Chạy code thật | [`interpreter.py:213`](D:/Documents/AI-Scientist-v2/ai_scientist/treesearch/interpreter.py:213), [`parallel_agent.py:1526`](D:/Documents/AI-Scientist-v2/ai_scientist/treesearch/parallel_agent.py:1526) | Interpreter ghi `runfile.py`, thực thi trong subprocess, thu output và exception. |
| Sửa lỗi runtime | [`parallel_agent.py:494`](D:/Documents/AI-Scientist-v2/ai_scientist/treesearch/parallel_agent.py:494) | `_debug` đưa source cũ và execution output vào prompt, tạo node con giữ lineage. |
| Bố trí dữ liệu local | [`config.py:209`](D:/Documents/AI-Scientist-v2/ai_scientist/treesearch/utils/config.py:209) | Tạo workspace `input/`, `working/`; copy/symlink dữ liệu từ `data_dir`. |
| Cho code khởi đầu | [`launch_scientist_bfts.py:205`](D:/Documents/AI-Scientist-v2/launch_scientist_bfts.py:205) | `--load_code` đọc file `.py` đi kèm idea, làm code tham khảo khởi đầu. |

Repo gốc chạy script Python trong môi trường local; luồng trên không phải trình tạo và
submit notebook Kaggle. Nó giảm tác động của lỗi bằng **thực thi rồi sửa theo lỗi thật**,
không bảo đảm script đầu tiên đúng.

Trong [`bfts_config.yaml`](D:/Documents/AI-Scientist-v2/bfts_config.yaml), timeout là 3600 giây,
`max_debug_depth=3`, `num_drafts=3`; các stage có giới hạn iteration riêng. Vì vậy v2 gốc
cũng có ngân sách tìm kiếm cấu hình được. Cơ chế tự khám phá này khác với GUI nơi user
chủ động quyết định từng lượt code và chạy.

## 3. So với MVP0 đang custom

MVP0 đã có nền template ở tầng notebook:

- Coder trả `CodePayload` gồm source, config và giải thích; không tự dựng JSON notebook.
- [`bundle.py`](D:/Documents/AI-Scientist-v2/ai_scientist/workbench/bundle.py:61) tự tạo notebook bằng
  `nbformat`, ghép runner cố định, context và source; validate schema và compile các cell.
- Preflight kiểm syntax, entrypoint `run(context, emit)`, config, seed, metadata và một số
  yêu cầu output. Đây là kiểm tra tĩnh, không thực thi loader/model.
- Context cấp mount `/kaggle/input/competitions/<slug>` và output directory chuẩn.
- [`notebook_runner.py`](D:/Documents/AI-Scientist-v2/ai_scientist/workbench/notebook_runner.py)
  phụ trách log, telemetry, result và xác nhận đầu ra khi notebook chạy thật.

Phần agent vẫn viết: loader dataset, chọn file/cột, ghép ảnh-label, split, model, loss,
metric, train và lưu artifact. Nếu agent dùng sai đường dẫn trong loader thì notebook
vẫn có thể hợp lệ về `nbformat` và syntax, nhưng lỗi lúc chạy trên Kaggle.

Do đó cần phân biệt:

| Loại lỗi | Lớp thích hợp xử lý |
|---|---|
| JSON role hoặc config sai schema | Structured payload và validation của backend |
| Notebook sai cấu trúc/cell syntax | Wrapper cố định + `nbformat.validate` + compile |
| Mount/file/cột CSV sai | Data manifest, path resolver, schema validation |
| Tensor/loss/metric/split sai | Data/model adapter + thực thi bước nhỏ trên dữ liệu thật |
| Kaggle/MCP disconnect, timeout, lỗi save/run | Submission/readiness/reconcile; training SDK không thay thế lớp này |

## 4. Công cụ tương tự

Các nhận xét “phù hợp” dưới đây là đánh giá cho nhu cầu của repo, không phải benchmark.

| Công cụ | Agent cần điền/viết gì? | Framework làm phần nào? | Đánh giá cho MVP0 |
|---|---|---|---|
| **PyTorch Lightning** | Model/loss qua `LightningModule`, dữ liệu qua loader/DataModule; có thể cấu hình YAML với LightningCLI | Trainer điều phối train/validation, device, gradient và callbacks. [Trainer](https://lightning.ai/docs/pytorch/stable/common/trainer), [DataModule](https://api.lightning.ai/docs/pytorch/stable/data/datamodule), [CLI/config](https://api.lightning.ai/docs/pytorch/stable/reference/cli/lightning_cli_advanced_2) | Lựa chọn phù hợp cho nhiều model PyTorch custom. Muốn agent chỉ điền config thì phải xây sẵn các model/data adapter được hỗ trợ. |
| **Transformers Trainer** | Model, dataset, `TrainingArguments`, metric; custom PyTorch model phải tuân contract về output/loss | Training loop cho hệ Transformers và model tương thích. [Tài liệu Trainer](https://huggingface.co/docs/transformers/en/main_classes/trainer) | Hợp cho workload dùng Hugging Face; CNN Soil với metric theo nhóm vẫn cần adapter riêng. |
| **TRL SFTTrainer** | Base model, dataset, SFTConfig; có thể phối hợp PEFT | Supervised finetuning cho language/vision-language model. [SFTTrainer](https://huggingface.co/docs/trl/en/sft_trainer) | Hợp cho profile finetune LLM/VLM về sau. Không phải template chung cho EDA/PCA hay mọi CNN. |
| **Axolotl** | YAML: base model, dataset/format, adapter, hyperparameters | CLI đọc config, nạp model, chuẩn bị dataset/tokenization, chạy training và lưu model. Có tài liệu dành cho agent. [SFT agent reference](https://docs.axolotl.ai/docs/agents/sft.html) | Gần nhất với ý “agent điền template” cho finetune LLM. Cần chuẩn bị model/package/data đúng môi trường Kaggle. |
| **LlamaFactory** | YAML có sẵn hoặc cấu hình bằng WebUI | CLI và GUI cho finetuning LLM/VLM; có example train/chat/export. [Repo và quickstart](https://github.com/hiyouga/LlamaFactory) | Lựa chọn khi muốn giao diện finetune có sẵn; tích hợp cả GUI riêng vào workbench sẽ tăng phạm vi công việc. |
| **Papermill** | Notebook mẫu và tham số, có thể từ YAML | Gán tham số rồi thực thi notebook. [Execute](https://papermill.readthedocs.io/en/latest/usage-execute.html) | Hữu ích nếu đã có nhiều notebook mẫu. Không cung cấp model/training/data loader, và wrapper MVP0 hiện đã giải quyết phần tạo notebook. |
| **AutoTrain Advanced** | Dataset và config; hướng low-code | Dự án có nhiều workflow training | Repo chính thức thông báo **không còn được bảo trì**, không thêm tính năng/sửa bug. Không chọn làm phụ thuộc mới. [Thông báo tại repo](https://github.com/huggingface/autotrain-advanced) |

Không nên bắt mọi tác vụ dùng một framework training. Tạo dữ liệu synthetic, EDA, PCA,
đọc ảnh và script xử lý thông thường vẫn cần một profile Python tổng quát.

## 5. Đề xuất triển khai tiếp theo

Đây là đề xuất từ research; **chưa triển khai lớp recipe/data adapter** trong thay đổi này.

### Ưu tiên 1: ngăn lỗi đường dẫn và contract trước

1. App/provider lưu manifest file thật và các đường mount xác minh được cho lượt chạy.
2. Cấp resolver qua context/SDK nhỏ: agent chọn file bằng đường dẫn tương đối trong manifest,
   không tự nối hoặc đoán prefix `/kaggle/input/...`.
3. Adapter kiểm CSV columns, dtype, label hữu hạn, mapping ảnh → sample và group split;
   báo rõ bước/cột/file thiếu trước khi khởi động training.
4. Chuẩn hóa exception theo bước: data/model/train/evaluate/output. Khi user bấm sửa, truyền
   code và traceback của đúng lượt trước đó, giữ nguyên phạm vi proposal đã duyệt.

Manifest/resolver phải phản ánh filesystem của runtime thật. Chỉ đổi prompt hoặc ghi một
danh sách đường dẫn chưa xác minh vào JSON không đủ để gọi đó là xác minh dữ liệu.

### Ưu tiên 2: template theo loại workload

```text
Notebook wrapper chung của app
    ├─ Python tổng quát: synthetic / EDA / PCA / xử lý ảnh
    ├─ PyTorch training: config + data adapter + model/loss/metric hooks
    └─ LLM finetune: config Axolotl/TRL + dataset adapter
```

Với CNN Soil hiện tại, có thể bắt đầu bằng template PyTorch đã biết chạy đúng. Vòng train,
device, deadline và logging do app sở hữu; agent chỉ thay config/model hooks đã được định
nghĩa. Khi có nhiều loại model hoặc cần distributed/mixed precision/callbacks phức tạp,
Lightning là lựa chọn để giảm code loop phải tự duy trì.

Với finetune LLM, đánh giá Axolotl trước nếu ưu tiên YAML; TRL nếu muốn điều khiển từ Python.
Chưa thể kết luận chạy ngay trên Kaggle: cần kiểm package/CUDA/VRAM, nguồn model/weights,
dataset, chế độ Internet và thời gian chạy của notebook. MVP0 hiện tắt Internet và giới hạn
package trong prompt; đây là phần tích hợp phải chuẩn bị nếu chọn SDK mới.

### Ưu tiên 3: kiểm tra runtime nhỏ trước GPU training

Một bước chạy loader + một forward/backward batch trên dữ liệu thật có thể phát hiện sớm
lỗi shape, file và loss mà kiểm tĩnh không thấy. Cần process/container được kiểm soát,
môi trường tương thích và dữ liệu mẫu thật. Không chạy code do agent tạo trực tiếp trong
process backend. Bước này cần thiết kế/triển khai riêng; chưa chạy trong phiên research này.

## 6. Chính sách số lượt đã thay đổi

User chọn: **user quyết định từng lượt, không giới hạn tổng số lượt**.

- Mỗi lần bấm tạo/sửa code gọi coder một lượt; lỗi không tự kích hoạt lượt coder kế tiếp.
- Bỏ quota 2 coder calls; có thể sửa cả khi bản hiện tại đã qua preflight, trước submit.
- Sau khi lượt chạy kết thúc, **Tạo lượt chạy mới** dùng cùng proposal đã duyệt và code đã
  lưu. App tạo ID/thư mục/slug Kaggle riêng, dựng lại notebook với context của run mới.
- Dùng lại code không tính là một lần gọi Codex. User chọn sửa code hoặc gửi Kaggle riêng.
- Lượt sửa nhận code và phần log lỗi được lưu từ run trước. Run cũ giữ identity và artifacts.
- Yêu cầu tạo lượt mới có request ID chống tạo trùng khi client gửi lại cùng request.
- Một request submit của một execution được xử lý idempotent. User có thể tạo bao nhiêu
  execution mới tùy ý; việc không gửi trùng request cũ không phải quota tổng cho user.
- Run UNKNOWN chỉ cho tạo lượt mới sau kiểm tra account Kaggle đang rảnh theo chính sách
  user đã chọn. Không xóa intent chưa rõ kết quả để gửi lại.
- Thời gian và dung lượng là ngân sách của **mỗi execution** đã duyệt; thay đổi số lượt
  không tự thay đổi model, dữ liệu, split, metric hoặc ngân sách mỗi lượt.

DB migration v3 thêm quan hệ run gốc/run mới và trường phân biệt CODEX/REUSE. Các proposal
cũ giữ nguyên dữ liệu approval; `coder_calls`/`training_attempts` cũ được đọc để tương thích
nhưng không còn được dùng để giới hạn các thao tác user.

### Mức kiểm chứng của thay đổi này

- Frontend `npm run build` thành công; Python workbench compile thành công.
- Backend khởi động, migration v3 hoàn tất qua startup, health trả `ok` và có các MCP tools.
- Đã mở run lịch sử trên GUI để xem counter mới và nút **Tạo lượt chạy mới**.
- Đã sao lưu các SQLite project trước migration tại `.workbench/backups/user-controlled-runs-v3/`.
- Chưa chạy test suite hoặc một lượt code/submit thật mới cho thay đổi này.
