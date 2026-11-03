import json
import mimetypes
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / 'backend' / 'uploads'
EXPORT_DIR = ROOT / 'backend' / 'exports'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title='Media Metadata Editor API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.heic', '.heif'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm'}
AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.flac', '.wav', '.ogg'}


def detect_media_type(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return 'image'
    if extension in VIDEO_EXTENSIONS:
        return 'video'
    if extension in AUDIO_EXTENSIONS:
        return 'audio'
    return 'unknown'


def format_bytes(value: int) -> str:
    units = ['B', 'KB', 'MB', 'GB']
    size = float(value)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f'{size:.2f} {units[index]}'


def normalize_tag_name(name: str) -> str:
    cleaned = ''.join(ch for ch in str(name).strip() if ch.isalnum())
    if not cleaned:
        return 'Title'
    return cleaned[0].upper() + cleaned[1:]


def safe_file_name(filename: str) -> str:
    clean = Path(filename).name
    if not clean or clean in {'.', '..'}:
        return 'upload.bin'
    return clean.replace('..', '_')


def safe_run(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        return {
            'returncode': completed.returncode,
            'stdout': completed.stdout,
            'stderr': completed.stderr,
        }
    except FileNotFoundError:
        return {'returncode': 127, 'stdout': '', 'stderr': f'Command not found: {command[0]}'}


def read_exiftool(path: Path) -> dict[str, Any]:
    exiftool = shutil.which('exiftool')
    if not exiftool:
        return {}

    result = safe_run([exiftool, '-j', '-n', str(path)])
    if result['returncode'] != 0:
        return {}

    payload = result['stdout'].strip()
    if not payload:
        return {}

    try:
        parsed = json.loads(payload)
        return parsed[0] if isinstance(parsed, list) and parsed else {}
    except json.JSONDecodeError:
        return {}


def read_ffprobe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return {}

    result = safe_run([ffprobe, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(path)])
    if result['returncode'] != 0:
        return {}

    payload = result['stdout'].strip()
    if not payload:
        return {}

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


def build_file_info(path: Path, media_type: str) -> dict[str, str]:
    stat = path.stat()
    return {
        'fileName': path.name,
        'fileSize': format_bytes(stat.st_size),
        'fileType': media_type.title(),
        'mimeType': mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
        'fileExtension': path.suffix.lower().lstrip('.') if path.suffix else 'unknown',
        'createdDate': datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
        'modifiedDate': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def build_fallback_details(media_type: str, payload: dict[str, Any]) -> dict[str, str]:
    if media_type == 'image':
        return {
            'Width': str(payload.get('ImageWidth') or payload.get('Width') or ''),
            'Height': str(payload.get('ImageHeight') or payload.get('Height') or ''),
            'Resolution': str(payload.get('ImageWidth') or payload.get('Width') or '') + ' x ' + str(payload.get('ImageHeight') or payload.get('Height') or ''),
            'ColorSpace': str(payload.get('ColorSpace') or 'sRGB'),
            'Orientation': str(payload.get('Orientation') or 'Horizontal (normal)'),
            'Compression': str(payload.get('Compression') or 'Metadata-only update'),
            'CameraMake': str(payload.get('Make') or ''),
            'CameraModel': str(payload.get('Model') or ''),
            'Lens': str(payload.get('LensModel') or payload.get('Lens') or ''),
            'ISO': str(payload.get('ISO') or ''),
            'Aperture': str(payload.get('ApertureValue') or payload.get('FNumber') or ''),
            'ShutterSpeed': str(payload.get('ExposureTime') or payload.get('ShutterSpeed') or ''),
            'FocalLength': str(payload.get('FocalLength') or ''),
        }

    if media_type == 'video':
        stream = payload.get('streams') or []
        video_stream = next((candidate for candidate in stream if candidate.get('codec_type') == 'video'), {})
        audio_stream = next((candidate for candidate in stream if candidate.get('codec_type') == 'audio'), {})
        format_info = payload.get('format') or {}
        width = video_stream.get('width') or ''
        height = video_stream.get('height') or ''
        resolution = f'{width} x {height}' if width and height else ''
        return {
            'Duration': str(format_info.get('duration') or video_stream.get('duration') or ''),
            'Resolution': resolution,
            'FPS': str(video_stream.get('r_frame_rate') or video_stream.get('avg_frame_rate') or ''),
            'VideoCodec': str(video_stream.get('codec_name') or ''),
            'AudioCodec': str(audio_stream.get('codec_name') or ''),
            'Bitrate': str(format_info.get('bit_rate') or ''),
            'PixelFormat': str(video_stream.get('pix_fmt') or ''),
            'ContainerFormat': str(format_info.get('format_name') or ''),
            'AudioSampleRate': str(audio_stream.get('sample_rate') or ''),
            'AudioChannels': str(audio_stream.get('channels') or ''),
        }

    if media_type == 'audio':
        stream = payload.get('streams') or []
        audio_stream = next((candidate for candidate in stream if candidate.get('codec_type') == 'audio'), {})
        format_info = payload.get('format') or {}
        return {
            'Duration': str(format_info.get('duration') or audio_stream.get('duration') or ''),
            'Codec': str(audio_stream.get('codec_name') or ''),
            'Bitrate': str(format_info.get('bit_rate') or ''),
            'SampleRate': str(audio_stream.get('sample_rate') or ''),
            'Channels': str(audio_stream.get('channels') or ''),
            'Artist': str(payload.get('artist') or ''),
            'Album': str(payload.get('album') or ''),
            'Genre': str(payload.get('genre') or ''),
            'TrackNumber': str(payload.get('track') or ''),
            'DiscNumber': str(payload.get('disc') or ''),
            'Year': str(payload.get('date') or payload.get('year') or ''),
        }

    return {}


def build_editable_fields(raw_metadata: dict[str, Any], media_type: str) -> dict[str, str]:
    base = {
        'Title': str(raw_metadata.get('Title') or raw_metadata.get('title') or ''),
        'Description': str(raw_metadata.get('Description') or raw_metadata.get('description') or ''),
        'Author': str(raw_metadata.get('Author') or raw_metadata.get('artist') or raw_metadata.get('Artist') or ''),
        'Creator': str(raw_metadata.get('Creator') or raw_metadata.get('creator') or ''),
        'Copyright': str(raw_metadata.get('Copyright') or raw_metadata.get('copyright') or ''),
        'Software': str(raw_metadata.get('Software') or raw_metadata.get('software') or ''),
        'Comment': str(raw_metadata.get('Comment') or raw_metadata.get('comment') or ''),
        'Artist': str(raw_metadata.get('Artist') or raw_metadata.get('artist') or ''),
        'Album': str(raw_metadata.get('Album') or raw_metadata.get('album') or ''),
        'Genre': str(raw_metadata.get('Genre') or raw_metadata.get('genre') or ''),
        'TrackNumber': str(raw_metadata.get('TrackNumber') or raw_metadata.get('track') or ''),
        'DiscNumber': str(raw_metadata.get('DiscNumber') or raw_metadata.get('disc') or ''),
        'Year': str(raw_metadata.get('Year') or raw_metadata.get('year') or raw_metadata.get('Date') or ''),
    }

    if media_type == 'image':
        base['CameraMake'] = str(raw_metadata.get('Make') or '')
        base['CameraModel'] = str(raw_metadata.get('Model') or '')
        base['Lens'] = str(raw_metadata.get('LensModel') or raw_metadata.get('Lens') or '')

    return {key: value for key, value in base.items() if value}


def collect_metadata(path: Path) -> dict[str, Any]:
    media_type = detect_media_type(path.name)
    exiftool_data = read_exiftool(path)
    ffprobe_data = read_ffprobe(path)

    details = build_fallback_details(media_type, ffprobe_data if media_type in {'video', 'audio'} else exiftool_data)
    if not details:
        details = {
            'Status': 'Metadata read via safe fallback mode',
            'Tooling': 'ExifTool/FFprobe unavailable',
        }

    file_info = build_file_info(path, media_type)
    editable = build_editable_fields(exiftool_data, media_type)
    if not editable:
        editable = {
            'Title': '',
            'Description': '',
            'Author': '',
            'Creator': '',
            'Copyright': '',
            'Software': '',
            'Comment': '',
            'Artist': '',
            'Album': '',
            'Genre': '',
            'TrackNumber': '',
            'DiscNumber': '',
            'Year': '',
        }

    return {
        'fileName': path.name,
        'mediaType': media_type,
        'tooling': {
            'exiftool': bool(shutil.which('exiftool')),
            'ffprobe': bool(shutil.which('ffprobe')),
        },
        'fileInfo': file_info,
        'details': details,
        'editableFields': editable,
        'rawMetadata': exiftool_data if exiftool_data else ffprobe_data,
    }


@app.get('/api/health')
def healthcheck() -> dict[str, Any]:
    return {
        'status': 'ok',
        'message': 'Media Metadata Editor API is ready.',
        'tooling': {
            'exiftool': bool(shutil.which('exiftool')),
            'ffprobe': bool(shutil.which('ffprobe')),
        },
    }


@app.post('/api/metadata')
async def read_media_metadata(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail='A file is required.')

    safe_name = safe_file_name(file.filename)
    target_path = UPLOAD_DIR / safe_name
    with target_path.open('wb') as destination:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            destination.write(chunk)

    response = collect_metadata(target_path)
    response['downloadUrl'] = f'/api/download/{safe_name}'
    return response


@app.post('/api/update-metadata')
async def update_metadata(file_name: str = Form(...), updates: str = Form('{}')) -> dict[str, Any]:
    clean_filename = safe_file_name(file_name)
    original_path = UPLOAD_DIR / clean_filename
    if not original_path.exists():
        raise HTTPException(status_code=404, detail='File was not found on the server.')

    exiftool = shutil.which('exiftool')
    if not exiftool:
        raise HTTPException(
            status_code=400,
            detail='ExifTool is not installed. Install it to write metadata without re-encoding the media.',
        )

    raw_updates = updates or '{}'
    try:
        payload = json.loads(raw_updates)
    except json.JSONDecodeError:
        payload = json.loads(raw_updates.encode('utf-8').decode('unicode_escape'))

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='Updates must be a JSON object.')

    destination_path = EXPORT_DIR / f'edited_{clean_filename}'
    if destination_path.exists():
        destination_path.unlink()
    shutil.copy2(original_path, destination_path)

    command = ['exiftool', '-overwrite_original']
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, (int, float)):
            command.append(f'-{normalize_tag_name(key)}={value}')
        elif str(value).strip():
            command.append(f'-{normalize_tag_name(key)}={str(value).strip()}')

    if len(command) == 2:
        return {'success': True, 'downloadUrl': f'/api/download/{destination_path.name}', 'message': 'No metadata changes were made.'}

    result = safe_run(command + [str(destination_path)])
    if result['returncode'] != 0:
        raise HTTPException(
            status_code=400,
            detail=result.get('stderr') or 'Unable to write metadata. Ensure ExifTool is available.',
        )

    return {'success': True, 'downloadUrl': f'/api/download/{destination_path.name}', 'message': 'Metadata saved.'}


@app.get('/api/download/{file_name}')
def download_file(file_name: str) -> FileResponse:
    candidate_paths = [EXPORT_DIR / file_name, UPLOAD_DIR / file_name]
    for candidate in candidate_paths:
        if candidate.exists():
            return FileResponse(candidate)
    raise HTTPException(status_code=404, detail='The requested file was not found.')
