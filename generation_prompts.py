"""Visible, language-aware generation instructions; original scene text is intact."""
import re


def language(prompt, requested='auto'):
    if requested in ('vi','en'): return requested
    return 'vi' if re.search(r'[ăâđêôơưĂÂĐÊÔƠƯ\u1ea0-\u1ef9]',prompt) else 'en'


def build_prompt(r, kind):
    vi = language(r.prompt,r.prompt_language)=='vi'
    ar=(r.aspect_ratio or r.size or '').lower()
    ratio='9:16' if any(x in ar for x in ('9:16','9/16','portrait','720x1280','1080x1920')) else ('16:9' if any(x in ar for x in ('16:9','16/9','landscape','1280x720','1920x1080')) else ('4:3' if '4:3' in ar else ('3:4' if '3:4' in ar else '1:1')))
    duration=getattr(r,'duration',None) or 10
    refs=r.reference_images or []
    has_ref=bool(refs or r.reference_image or r.image or getattr(r,'image_url',None) or getattr(r,'images',None))
    coherent=r.generation_mode=='coherent'
    if vi:
        parts=[f"Tạo một {'video dài '+str(duration)+' giây' if kind=='video' else 'ảnh'}, tỷ lệ {ratio}."]
        parts.append('Đây là một cảnh trong cùng kịch bản. Giữ nhất quán nhân vật, khuôn mặt, trang phục, đạo cụ và phong cách từ bộ ảnh tham chiếu và các cảnh trước trong hội thoại. Chỉ tạo riêng cảnh mô tả bên dưới; không gộp nhiều cảnh thành một video dài.' if coherent else 'Tạo kết quả độc lập cho yêu cầu này, không lấy ngữ cảnh hay nhân vật từ các hội thoại trước.')
        names={'character':'nhận dạng nhân vật','background':'bối cảnh nền','scene':'bố cục cảnh','first_frame':'khung hình đầu','reference':'tham khảo hình ảnh'}
        if refs:
            roles=r.reference_roles or ['reference']*len(refs)
            parts.append(('Dùng bộ ảnh tham chiếu đã gửi ở đầu hội thoại: ' if coherent else 'Dùng toàn bộ ảnh đính kèm: ')+'; '.join(f'Ảnh {i+1}: {names[role]}' for i,role in enumerate(roles))+'. Chỉ dùng làm khung hình đầu khi được gán vai trò đó; không làm collage/slideshow từ bộ ảnh.')
        elif has_ref:parts.append('Dùng ảnh đính kèm làm tham chiếu, giữ nhận dạng nhân vật. Không tự coi ảnh là khung hình đầu nếu mô tả không yêu cầu.')
        if coherent and r.continuity_notes:parts.append('Quy ước chung cho chuỗi: '+r.continuity_notes.strip())
        parts.append('Mô tả cảnh:\n'+r.prompt.strip())
    else:
        parts=[f"Create one {str(duration)+'-second video' if kind=='video' else 'image'} with a {ratio} aspect ratio."]
        parts.append('This is one scene in the same story sequence. Keep the character identities, faces, clothing, props and visual style consistent with the reference images and earlier scenes in this conversation. Generate only the scene below; do not combine the sequence into one long video.' if coherent else 'Generate an independent result for this request. Do not reuse characters or context from previous conversations.')
        names={'character':'character identity','background':'background','scene':'scene and composition','first_frame':'starting frame','reference':'visual reference'}
        if refs:
            roles=r.reference_roles or ['reference']*len(refs)
            parts.append(('Use the reference images established at the beginning of this conversation: ' if coherent else 'Use ALL images attached to this message: ')+'; '.join(f'Image {i+1}: {names[role]}' for i,role in enumerate(roles))+'. Use a starting frame only for that role; do not make a collage or slideshow from the references.')
        elif has_ref:parts.append('Use the attached image as a visual/character reference. Do not automatically treat it as the starting frame unless requested.')
        if coherent and r.continuity_notes:parts.append('Shared sequence rules: '+r.continuity_notes.strip())
        parts.append('Scene instructions:\n'+r.prompt.strip())
    if getattr(r,'reference_files',None):
        parts.append(('Tài liệu tham chiếu trong hội thoại: ' if vi else 'Reference documents in this conversation: ')+', '.join(x['name'] for x in r.reference_files)+('. Dùng nội dung liên quan để thực hiện mô tả cảnh.' if vi else '. Use relevant content to follow the scene instructions.'))
    if getattr(r,'resolution',None):parts.append(('Yêu cầu chất lượng: ' if vi else 'Quality requirements: ')+r.resolution)
    if r.extra:parts.append(r.extra)
    return '\n\n'.join(parts)
