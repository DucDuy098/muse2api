"""Validation for local reference images used by persisted batch requests."""
import base64
import binascii

ROLES = {'reference', 'character', 'scene', 'background', 'first_frame'}


def validate_references(images, roles=None):
    if not isinstance(images, list) or len(images) > 8:
        raise ValueError('Chọn tối đa 8 ảnh mẫu')
    roles = roles if roles is not None else ['reference'] * len(images)
    if not isinstance(roles, list) or len(roles) != len(images) or any(r not in ROLES for r in roles):
        raise ValueError('Vai trò ảnh mẫu không hợp lệ')
    total = 0
    for value in images:
        if not isinstance(value, str) or len(value) > 7 * 1024 * 1024:
            raise ValueError('Mỗi ảnh tối đa 5 MB')
        header, sep, encoded = value.partition(',')
        if not sep or header not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'):
            raise ValueError('Ảnh mẫu cần là PNG, JPG hoặc WEBP')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Ảnh mẫu bị lỗi base64')
        valid = ((header.startswith('data:image/png;') and data.startswith(b'\x89PNG\r\n\x1a\n')) or
                 (header.startswith('data:image/jpeg;') and data.startswith(b'\xff\xd8\xff')) or
                 (header.startswith('data:image/webp;') and data.startswith(b'RIFF') and data[8:12] == b'WEBP'))
        if not valid or not data or len(data) > 5 * 1024 * 1024:
            raise ValueError('Ảnh không hợp lệ hoặc lớn hơn 5 MB')
        total += len(data)
    if total > 20 * 1024 * 1024:
        raise ValueError('Tổng ảnh mẫu tối đa 20 MB')
    return images, roles
