const labels:Record<string,string>={reference_only:'Chỉ có liên kết · chưa đọc',provided_text:'Có nội dung được cung cấp',
  extracted:'Đã trích text',partial:'Text trích một phần',no_text:'Không có text · có thể cần OCR',locked:'PDF khóa mật khẩu',
  error:'Trích text lỗi',file_reference:'Có file gốc · chưa trích text'};

export const statusText=(status:string)=>labels[status] || status;
