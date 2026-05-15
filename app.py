import os
import time
import uuid
import base64
import threading
import tempfile
import mimetypes
import requests
from io import BytesIO
from PIL import Image
from flask import Flask, request, jsonify, render_template_string, send_from_directory

app = Flask(__name__)

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

JOBS = {}

DEFAULT_API_BASE = os.environ.get("IMAGE_API_BASE", "")
DEFAULT_API_KEY = os.environ.get("IMAGE_API_KEY", "")
DEFAULT_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2")

SIZE_MAP = {
    "1:1": {
        "1k": "1024x1024",
        "2k": "2048x2048",
        "4k": "2880x2880",
    },
    "3:2": {
        "1k": "1536x1024",
        "2k": "2048x1360",
        "4k": "3520x2336",
    },
    "2:3": {
        "1k": "1024x1536",
        "2k": "1360x2048",
        "4k": "2336x3520",
    },
    "4:3": {
        "1k": "1024x768",
        "2k": "2048x1536",
        "4k": "3312x2480",
    },
    "3:4": {
        "1k": "768x1024",
        "2k": "1536x2048",
        "4k": "2480x3312",
    },
    "5:4": {
        "1k": "1280x1024",
        "2k": "2560x2048",
        "4k": "3216x2576",
    },
    "4:5": {
        "1k": "1024x1280",
        "2k": "2048x2560",
        "4k": "2576x3216",
    },
    "16:9": {
        "1k": "1536x864",
        "2k": "2048x1152",
        "4k": "3840x2160",
    },
    "9:16": {
        "1k": "864x1536",
        "2k": "1152x2048",
        "4k": "2160x3840",
    },
    "2:1": {
        "1k": "2048x1024",
        "2k": "2688x1344",
        "4k": "3840x1920",
    },
    "1:2": {
        "1k": "1024x2048",
        "2k": "1344x2688",
        "4k": "1920x3840",
    },
    "3:1": {
        "1k": "1881x836",
        "2k": "3072x1024",
        "4k": "3840x1280",
    },
    "1:3": {
        "1k": "887x1774",
        "2k": "1024x3072",
        "4k": "1280x3840",
    },
    "21:9": {
        "1k": "2016x864",
        "2k": "2688x1152",
        "4k": "3840x1648",
    },
    "9:21": {
        "1k": "864x2016",
        "2k": "1152x2688",
        "4k": "1648x3840",
    },
}


HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>GPT Image-2 使用中转api生成/修改图片工具</title>
    <style>
        body {
            font-family: Arial, "Microsoft YaHei", sans-serif;
            max-width: 1100px;
            margin: 40px auto;
            background: #f5f5f5;
        }
        .box {
            background: white;
            padding: 24px;
            border-radius: 12px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        }
        h1 {
            margin-top: 0;
        }
        label {
            display: block;
            margin-top: 16px;
            font-weight: bold;
        }
        input, textarea, select {
            width: 100%;
            box-sizing: border-box;
            padding: 10px;
            margin-top: 6px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 14px;
        }
        textarea {
            height: 120px;
        }
        button {
            margin-top: 20px;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            background: #1677ff;
            color: white;
            font-size: 16px;
            cursor: pointer;
        }
        button:disabled {
            background: #999;
            cursor: not-allowed;
        }
        .row {
            display: flex;
            gap: 16px;
        }
        .col {
            flex: 1;
        }
        .tip {
            color: #666;
            font-size: 13px;
            line-height: 1.6;
        }
        .status {
            margin-top: 24px;
            padding: 16px;
            border-radius: 8px;
            background: #f6ffed;
            border: 1px solid #b7eb8f;
            white-space: pre-wrap;
        }
        .error {
            margin-top: 24px;
            padding: 16px;
            border-radius: 8px;
            background: #fff1f0;
            border: 1px solid #ffa39e;
            color: #cf1322;
            white-space: pre-wrap;
        }
        .result {
            margin-top: 24px;
        }
        img {
            max-width: 100%;
            border-radius: 8px;
            border: 1px solid #ddd;
            margin-top: 12px;
        }
        code {
            background: #f1f1f1;
            padding: 2px 5px;
            border-radius: 4px;
        }
        .small {
            font-size: 13px;
            color: #666;
        }
    </style>
</head>
<body>
<div class="box">
    <h1>GPT Image-2 使用中转api生成/修改图片工具</h1>

    <label>模式</label>
    <select id="mode" onchange="onModeChange()">
        <option value="generations">图片生成 /v1/images/generations</option>
        <option value="edits">图片修改 /v1/images/edits</option>
    </select>

    <label>中转站 API Base</label>
    <input id="api_base" value="{{ default_api_base }}" placeholder="例如：https://somewhat-router.com">

    <label>API Key</label>
    <input id="api_key" type="password" value="{{ default_api_key }}" placeholder="sk-xxxxxxxxx">

    <label>模型名</label>
    <input id="model" value="{{ default_model }}" placeholder="例如：gpt-image-2">

    <div class="row">
        <div class="col">
            <label>图片比例 size</label>
            <select id="aspect" onchange="updateActualSize()">
                <option value="1:1">1:1</option>
                <option value="3:2">3:2</option>
                <option value="2:3" selected>2:3</option>
                <option value="4:3">4:3</option>
                <option value="3:4">3:4</option>
                <option value="5:4">5:4</option>
                <option value="4:5">4:5</option>
                <option value="16:9">16:9</option>
                <option value="9:16">9:16</option>
                <option value="2:1">2:1</option>
                <option value="1:2">1:2</option>
                <option value="3:1">3:1</option>
                <option value="1:3">1:3</option>
                <option value="21:9">21:9</option>
                <option value="9:21">9:21</option>
            </select>
        </div>

        <div class="col">
            <label>输出分辨率档位</label>
            <select id="resolution" onchange="updateActualSize()">
                <option value="1k" selected>1k</option>
                <option value="2k">2k</option>
                <option value="4k">4k</option>
            </select>
        </div>
    </div>

    <label>实际传给接口的 size</label>
    <input id="actual_size" readonly>

    <label>质量 quality</label>
    <select id="quality">
        <option value="auto">auto</option>
        <option value="low">low</option>
        <option value="medium">medium</option>
        <option value="high" selected>high</option>
    </select>

    <label>提示词 prompt</label>
    <textarea id="prompt" placeholder="请输入图片生成或修改提示词"></textarea>

    <div id="edit_inputs" style="display:none;">
        <label>上传本地图片，可多选，用于修改或参考</label>
        <input id="local_images" type="file" accept="image/*" multiple>

        <label>远程图片 URL，每行一个，用于修改或参考</label>
        <textarea id="remote_urls" placeholder="https://example.com/a.png&#10;https://example.com/b.jpg"></textarea>

        <label>图片字段名</label>
        <select id="image_field_name">
            <option value="image" selected>image，OpenAI 常见格式</option>
            <option value="image[]">image[]，部分中转站格式</option>
        </select>

        <p class="tip">
            修改模式会请求 <code>/v1/images/edits</code>。如果中转站要求字段名为 <code>image[]</code>，请切换上面的选项。
        </p>
    </div>

    <button id="btn" onclick="startJob()">开始</button>

    <p class="tip">
        当前工具会根据模式请求：
        <br>
        生成：<code>/v1/images/generations</code>
        <br>
        修改：<code>/v1/images/edits</code>
        <br>
        如果中转站没有调用记录，请查看终端日志中的请求 URL、状态码和返回内容。
    </p>

    <div id="status" class="status" style="display:none;"></div>
    <div id="error" class="error" style="display:none;"></div>
    <div id="result" class="result"></div>
</div>

<script>
const SIZE_MAP = {{ size_map_json | safe }};

function updateActualSize() {
    const aspect = document.getElementById("aspect").value;
    const resolution = document.getElementById("resolution").value;
    const actual = SIZE_MAP[aspect][resolution];
    document.getElementById("actual_size").value = actual;
}

function onModeChange() {
    const mode = document.getElementById("mode").value;
    const editInputs = document.getElementById("edit_inputs");
    editInputs.style.display = mode === "edits" ? "block" : "none";
}

updateActualSize();
onModeChange();

let pollingTimer = null;

function setStatus(text) {
    const el = document.getElementById("status");
    el.style.display = "block";
    el.innerText = text;
}

function setError(text) {
    const el = document.getElementById("error");
    el.style.display = "block";
    el.innerText = text;
}

function clearError() {
    const el = document.getElementById("error");
    el.style.display = "none";
    el.innerText = "";
}

function clearResult() {
    document.getElementById("result").innerHTML = "";
}

async function startJob() {
    clearError();
    clearResult();

    const btn = document.getElementById("btn");
    btn.disabled = true;

    const mode = document.getElementById("mode").value;

    const form = new FormData();
    form.append("mode", mode);
    form.append("api_base", document.getElementById("api_base").value.trim());
    form.append("api_key", document.getElementById("api_key").value.trim());
    form.append("model", document.getElementById("model").value.trim());
    form.append("aspect", document.getElementById("aspect").value);
    form.append("resolution", document.getElementById("resolution").value);
    form.append("size", document.getElementById("actual_size").value);
    form.append("quality", document.getElementById("quality").value);
    form.append("prompt", document.getElementById("prompt").value.trim());
    form.append("image_field_name", document.getElementById("image_field_name").value);

    if (mode === "edits") {
        const files = document.getElementById("local_images").files;
        for (let i = 0; i < files.length; i++) {
            form.append("local_images", files[i]);
        }
        form.append("remote_urls", document.getElementById("remote_urls").value.trim());
    }

    setStatus("正在提交本地任务...");

    try {
        const res = await fetch("/start", {
            method: "POST",
            body: form
        });

        const data = await res.json();

        if (!data.ok) {
            setError(data.error || "提交失败");
            btn.disabled = false;
            return;
        }

        const jobId = data.job_id;
        setStatus("任务已提交，任务 ID：" + jobId);

        if (pollingTimer) {
            clearInterval(pollingTimer);
        }

        pollingTimer = setInterval(() => pollStatus(jobId), 1500);

    } catch (e) {
        setError(String(e));
        btn.disabled = false;
    }
}

async function pollStatus(jobId) {
    const btn = document.getElementById("btn");

    try {
        const res = await fetch("/status/" + jobId);
        const data = await res.json();

        if (!data.ok) {
            setError(data.error || "查询状态失败");
            clearInterval(pollingTimer);
            btn.disabled = false;
            return;
        }

        let text = "";
        text += "任务 ID：" + jobId + "\\n";
        text += "模式：" + data.mode + "\\n";
        text += "请求端点：" + data.endpoint + "\\n";
        text += "状态：" + data.status + "\\n";
        text += "进度：" + data.progress + "%\\n";
        text += "消息：" + data.message + "\\n";
        text += "请求尺寸：" + data.request_size + "\\n";
        text += "耗时：" + data.elapsed + " 秒\\n";

        if (data.upload_count !== undefined) {
            text += "输入图片数量：" + data.upload_count + "\\n";
        }

        setStatus(text);

        if (data.status === "done") {
            clearInterval(pollingTimer);
            btn.disabled = false;

            let html = "<h3>结果</h3>";
            if (data.image_files && data.image_files.length > 0) {
                for (const f of data.image_files) {
                    html += `<p class="small">文件：${f}</p>`;
                    html += `<img src="/outputs/${f}">`;
                }
            } else {
                html += "<p>任务完成，但没有图片文件。</p>";
            }
            document.getElementById("result").innerHTML = html;
        }

        if (data.status === "error") {
            clearInterval(pollingTimer);
            btn.disabled = false;
            setError(data.error || data.message || "任务失败");
        }

    } catch (e) {
        clearInterval(pollingTimer);
        btn.disabled = false;
        setError(String(e));
    }
}
</script>
</body>
</html>
"""


def update_job(job_id, **kwargs):
    if job_id in JOBS:
        JOBS[job_id].update(kwargs)


def save_base64_image(b64_data, output_path):
    image_bytes = base64.b64decode(b64_data)
    img = Image.open(BytesIO(image_bytes))
    img.save(output_path)


def save_url_image(url, output_path):
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(r.content)


def save_response_images(data, job_id):
    image_files = []

    if "data" not in data or not data["data"]:
        raise RuntimeError(f"返回结果中没有 data 图片数据：{str(data)[:3000]}")

    for idx, item in enumerate(data["data"]):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        image_file = f"image_{timestamp}_{job_id[:8]}_{idx + 1}.png"
        output_path = os.path.join(OUTPUT_DIR, image_file)

        if "b64_json" in item:
            save_base64_image(item["b64_json"], output_path)
            image_files.append(image_file)
        elif "url" in item:
            save_url_image(item["url"], output_path)
            image_files.append(image_file)
        else:
            raise RuntimeError(f"未识别的图片返回格式：{str(item)[:3000]}")

    return image_files


def download_remote_images(remote_urls):
    temp_files = []

    urls = []
    for line in remote_urls.splitlines():
        line = line.strip()
        if line:
            urls.append(line)

    for idx, url in enumerate(urls):
        r = requests.get(url, timeout=120)
        r.raise_for_status()

        content_type = r.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".png"

        temp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp.write(r.content)
        temp.close()

        temp_files.append({
            "path": temp.name,
            "filename": f"remote_{idx + 1}{ext}",
            "content_type": content_type or "image/png",
        })

    return temp_files


def generation_worker(job_id, payload):
    start = time.time()

    api_base = payload["api_base"].rstrip("/")
    endpoint = f"{api_base}/v1/images/generations"

    headers = {
        "Authorization": f"Bearer {payload['api_key']}",
        "Content-Type": "application/json",
    }

    body = {
        "model": payload["model"],
        "prompt": payload["prompt"],
        "size": payload["size"],
        "quality": payload["quality"],
        "n": 1,
    }

    print("\n===== IMAGE GENERATION REQUEST =====")
    print("endpoint:", endpoint)
    print("model:", body["model"])
    print("size:", body["size"])
    print("quality:", body["quality"])
    print("prompt:", body["prompt"][:200])
    print("====================================\n")

    try:
        update_job(
            job_id,
            status="running",
            progress=10,
            message="正在请求图片生成端点...",
            elapsed=int(time.time() - start),
        )

        response = requests.post(endpoint, headers=headers, json=body, timeout=360)

        print("generation status:", response.status_code)
        print("generation response preview:", response.text[:1000])

        update_job(
            job_id,
            progress=70,
            message="接口已返回，正在解析结果...",
            elapsed=int(time.time() - start),
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"请求失败，状态码：{response.status_code}\n\n{response.text[:5000]}"
            )

        data = response.json()

        update_job(
            job_id,
            progress=85,
            message="正在保存图片...",
            elapsed=int(time.time() - start),
        )

        image_files = save_response_images(data, job_id)

        update_job(
            job_id,
            status="done",
            progress=100,
            message="生成完成",
            image_files=image_files,
            elapsed=int(time.time() - start),
        )

    except Exception as e:
        update_job(
            job_id,
            status="error",
            progress=100,
            message="生成失败",
            error=str(e),
            elapsed=int(time.time() - start),
        )


def edits_worker(job_id, payload, local_file_infos):
    start = time.time()

    api_base = payload["api_base"].rstrip("/")
    endpoint = f"{api_base}/v1/images/edits"

    headers = {
        "Authorization": f"Bearer {payload['api_key']}",
    }

    data = {
        "model": payload["model"],
        "prompt": payload["prompt"],
        "size": payload["size"],
        "quality": payload["quality"],
        "n": "1",
    }

    image_field_name = payload.get("image_field_name", "image")

    opened_files = []
    temp_remote_files = []

    try:
        update_job(
            job_id,
            status="running",
            progress=10,
            message="正在准备图片文件...",
            elapsed=int(time.time() - start),
        )

        temp_remote_files = download_remote_images(payload.get("remote_urls", ""))

        all_file_infos = local_file_infos + temp_remote_files

        if not all_file_infos:
            raise RuntimeError("修改模式至少需要上传一张本地图片或填写一个远程图片 URL。")

        files = []

        for idx, info in enumerate(all_file_infos):
            path = info["path"]
            filename = info["filename"]
            content_type = info.get("content_type") or mimetypes.guess_type(filename)[0] or "image/png"

            f = open(path, "rb")
            opened_files.append(f)

            files.append(
                (
                    image_field_name,
                    (
                        filename,
                        f,
                        content_type,
                    ),
                )
            )

        print("\n===== IMAGE EDIT REQUEST =====")
        print("endpoint:", endpoint)
        print("model:", data["model"])
        print("size:", data["size"])
        print("quality:", data["quality"])
        print("image_field_name:", image_field_name)
        print("image_count:", len(files))
        print("prompt:", data["prompt"][:200])
        print("==============================\n")

        update_job(
            job_id,
            progress=30,
            message=f"正在请求图片修改端点，输入图片数量：{len(files)}",
            upload_count=len(files),
            elapsed=int(time.time() - start),
        )

        response = requests.post(
            endpoint,
            headers=headers,
            data=data,
            files=files,
            timeout=360,
        )

        print("edit status:", response.status_code)
        print("edit response preview:", response.text[:1000])

        update_job(
            job_id,
            progress=70,
            message="接口已返回，正在解析结果...",
            elapsed=int(time.time() - start),
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"请求失败，状态码：{response.status_code}\n\n{response.text[:5000]}"
            )

        resp_data = response.json()

        update_job(
            job_id,
            progress=85,
            message="正在保存图片...",
            elapsed=int(time.time() - start),
        )

        image_files = save_response_images(resp_data, job_id)

        update_job(
            job_id,
            status="done",
            progress=100,
            message="修改完成",
            image_files=image_files,
            elapsed=int(time.time() - start),
        )

    except Exception as e:
        update_job(
            job_id,
            status="error",
            progress=100,
            message="修改失败",
            error=str(e),
            elapsed=int(time.time() - start),
        )

    finally:
        for f in opened_files:
            try:
                f.close()
            except Exception:
                pass

        for info in temp_remote_files:
            try:
                os.remove(info["path"])
            except Exception:
                pass

        for info in local_file_infos:
            try:
                os.remove(info["path"])
            except Exception:
                pass


@app.route("/", methods=["GET"])
def index():
    import json

    return render_template_string(
        HTML,
        size_map_json=json.dumps(SIZE_MAP, ensure_ascii=False),
        default_api_base=DEFAULT_API_BASE,
        default_api_key=DEFAULT_API_KEY,
        default_model=DEFAULT_MODEL,
    )


@app.route("/start", methods=["POST"])
def start():
    mode = request.form.get("mode", "generations").strip()

    payload = {
        "mode": mode,
        "api_base": request.form.get("api_base", "").strip(),
        "api_key": request.form.get("api_key", "").strip(),
        "model": request.form.get("model", "").strip(),
        "prompt": request.form.get("prompt", "").strip(),
        "size": request.form.get("size", "").strip(),
        "quality": request.form.get("quality", "high").strip(),
        "remote_urls": request.form.get("remote_urls", "").strip(),
        "image_field_name": request.form.get("image_field_name", "image").strip(),
    }

    for key in ["api_base", "api_key", "model", "prompt", "size"]:
        if not payload[key]:
            return jsonify({
                "ok": False,
                "error": f"缺少参数：{key}"
            })

    job_id = str(uuid.uuid4())

    if mode == "generations":
        endpoint = f"{payload['api_base'].rstrip('/')}/v1/images/generations"
    elif mode == "edits":
        endpoint = f"{payload['api_base'].rstrip('/')}/v1/images/edits"
    else:
        return jsonify({
            "ok": False,
            "error": f"未知模式：{mode}"
        })

    JOBS[job_id] = {
        "mode": mode,
        "endpoint": endpoint,
        "status": "queued",
        "progress": 0,
        "message": "任务已创建，等待执行",
        "error": None,
        "image_files": [],
        "created_at": time.time(),
        "elapsed": 0,
        "request_size": payload["size"],
        "upload_count": 0,
    }

    if mode == "generations":
        thread = threading.Thread(target=generation_worker, args=(job_id, payload))
        thread.daemon = True
        thread.start()

    else:
        local_file_infos = []

        files = request.files.getlist("local_images")

        for idx, file in enumerate(files):
            if not file or not file.filename:
                continue

            original_name = file.filename
            ext = os.path.splitext(original_name)[1] or ".png"

            temp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            file.save(temp.name)
            temp.close()

            local_file_infos.append({
                "path": temp.name,
                "filename": original_name,
                "content_type": file.content_type or mimetypes.guess_type(original_name)[0] or "image/png",
            })

        thread = threading.Thread(target=edits_worker, args=(job_id, payload, local_file_infos))
        thread.daemon = True
        thread.start()

    return jsonify({
        "ok": True,
        "job_id": job_id
    })


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    job = JOBS.get(job_id)

    if not job:
        return jsonify({
            "ok": False,
            "error": "任务不存在"
        })

    if job.get("status") in ["queued", "running"]:
        job["elapsed"] = int(time.time() - job.get("created_at", time.time()))

    return jsonify({
        "ok": True,
        **job
    })


@app.route("/outputs/<filename>")
def outputs(filename):
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    print("默认 API Base:", DEFAULT_API_BASE)
    print("默认模型:", DEFAULT_MODEL)
    print("API Key 是否已设置:", "是" if DEFAULT_API_KEY else "否")
    app.run(host="127.0.0.1", port=7860, debug=True)
