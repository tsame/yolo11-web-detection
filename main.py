import streamlit as st
from inference_sdk import InferenceHTTPClient
from PIL import Image, ImageDraw, ImageFont
import io
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch # Memindahkan impor inch untuk mencegah UnboundLocalError
import time

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="Analisis & Penilaian UI Otomatis",
    page_icon="🤖",
    layout="wide"
)

# ==============================================================================
# 1. KONFIGURASI MODEL (HARDCODED SESUAI PERMINTAAN)
# ==============================================================================

# Kredensial hardcoded (HANYA UNTUK PROYEK SKRIPSI/LOKAL)
API_KEY = "2jDbzJsXWACR5parVNix"  
PROJECT_ID = "penilaian-ui-web-ax2rc"
VERSION_NUM = 2

COMBINED_MODEL_ID = f"{PROJECT_ID}/{int(VERSION_NUM)}"

# --- Inisialisasi Klien (dilakukan sekali) ---
@st.cache_resource
def load_inference_client(api_key):
    """Membuat klien inferensi dengan kredensial yang diberikan."""
    try:
        client = InferenceHTTPClient(
            api_url="https://serverless.roboflow.com",
            api_key=api_key
        )
        return client
    except Exception as e:
        st.sidebar.error(f"Gagal membuat klien Roboflow. Pastikan API Key dan koneksi internet berfungsi. Detail: {e}")
        return None

client = load_inference_client(API_KEY)


# ==============================================================================
# 2. FUNGSI HELPER (Draw Anotasi & PDF Report)
# ==============================================================================

def draw_annotations(image, predictions):
    """Menggambar bounding box dan label pada gambar."""
    annotated_image = image.copy().convert("RGB")
    draw = ImageDraw.Draw(annotated_image)
    
    try:
        font = ImageFont.truetype("arial.ttf", size=15)
    except IOError:
        font = ImageFont.load_default()

    for pred in predictions:
        x_center, y_center, width, height = pred['x'], pred['y'], pred['width'], pred['height']
        x_min = x_center - (width / 2)
        y_min = y_center - (height / 2)
        x_max = x_center + (width / 2)
        y_max = y_center + (height / 2)
        
        label = f"{pred['class']} ({pred['confidence']:.0%})"
        color = "red"
        
        draw.rectangle([x_min, y_min, x_max, y_max], outline=color, width=2)
        
        try:
            text_bbox = draw.textbbox((x_min, y_min), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
        except AttributeError:
             text_width, text_height = draw.textsize(label, font=font)
             
        text_y_min = y_min - text_height - 2
        
        draw.rectangle([x_min, text_y_min, x_min + text_width, y_min], fill=color)
        draw.text((x_min, text_y_min), label, fill="white", font=font)

    return annotated_image

def generate_pdf_report(scores, image_path, image_name):
    """Membuat laporan PDF dengan penilaian dalam bentuk tabel dan gambar di satu halaman."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    elements = []
    
    # --- Header Dokumen ---
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph("<b>Laporan Penilaian Desain UI</b>", styles['h1']))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(f"Tanggal Laporan: {current_time}", styles['Normal']))
    elements.append(Paragraph(f"Screenshot Asal: {image_name}", styles['Normal']))
    elements.append(Spacer(1, 0.4 * inch))

    # --- Gambar Hasil Deteksi ---
    if image_path and os.path.exists(image_path):
        try:
            pil_img = Image.open(image_path)
            original_width, original_height = pil_img.size
            
            # Batas dimensi frame halaman
            max_img_width_inch = 5.3
            max_img_height_inch = 6.3
            
            # Konversi inch ke point (72 points per inch)
            max_img_width_pt = max_img_width_inch * inch
            max_img_height_pt = max_img_height_inch * inch
            
            img_width_pt = original_width
            img_height_pt = original_height
            
            # 1. Skala berdasarkan Lebar Maksimal
            if img_width_pt > max_img_width_pt:
                img_height_pt = img_height_pt * (max_img_width_pt / img_width_pt)
                img_width_pt = max_img_width_pt

            # 2. Skala berdasarkan Tinggi Maksimal (jika masih terlalu tinggi)
            if img_height_pt > max_img_height_pt:
                img_width_pt = img_width_pt * (max_img_height_pt / img_height_pt)
                img_height_pt = max_img_height_pt

            from reportlab.platypus import Image as PlatypusImage
            img = PlatypusImage(image_path, width=img_width_pt, height=img_height_pt)
            
            elements.append(Paragraph("<b>Gambar Hasil Deteksi</b>", styles['h2']))
            elements.append(Spacer(1, 0.1 * inch))
            elements.append(img)
            elements.append(Spacer(1, 0.4 * inch))
            
        except Exception as e:
            elements.append(Paragraph(f"<i>Gagal menambahkan gambar ke PDF: {e}</i>", styles['Normal']))
            elements.append(Spacer(1, 0.2 * inch))
    else:
        elements.append(Paragraph("<i>Gambar hasil deteksi tidak tersedia.</i>", styles['Normal']))
        elements.append(Spacer(1, 0.2 * inch))

    # --- Penilaian Umum (Bawaan) dalam Tabel ---
    elements.append(Paragraph("<b>Penilaian Umum (Bawaan Sistem)</b>", styles['h2']))
    elements.append(Spacer(1, 0.1 * inch))

    data_umum = [
        ["Kategori", "Penilaian"],
        ["Font/Tipografi", scores.get('penilaian_font', '-')],
        ["Warna/Skema", scores.get('penilaian_color', '-')],
        ["Skala/Hierarki", scores.get('penilaian_scale', '-')]
    ]
    table_umum = Table(data_umum, colWidths=[2*inch, 4.5*inch]) 
    table_umum.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('WORDWRAP', (1,1), (1,-1), Paragraph),
    ]))
    elements.append(table_umum)
    elements.append(Spacer(1, 0.4 * inch))

    # --- Penilaian Elemen Dinamis dalam SATU TABEL ---
    elements.append(Paragraph("<b>Penilaian Elemen (Hasil Deteksi Model)</b>", styles['h2']))
    elements.append(Spacer(1, 0.1 * inch))

    # 1. Kumpulkan semua ID elemen dinamis yang unik
    all_dynamic_ids = set()
    for key in scores.keys():
        if key.startswith("penilaian_") and key not in ['penilaian_font', 'penilaian_color', 'penilaian_scale']:
            all_dynamic_ids.add(key.replace('penilaian_', ''))
        elif key.startswith("catatan_"):
            all_dynamic_ids.add(key.replace('catatan_', ''))

    # 2. Siapkan data tabel
    final_table_data = [
        [
            "Nama Elemen", 
            "Penilaian UI", 
            "Penilaian Tambahan (Catatan)" # Ganti Catatan menjadi Penilaian Tambahan
        ]
    ]

    # 3. Iterasi dan gabungkan skor per elemen
    sorted_ids = sorted(list(all_dynamic_ids))

    for element_id in sorted_ids:
        # Ambil nilai Penilaian UI (utamakan)
        penilaian_ui = scores.get(f'penilaian_{element_id}', 'Tidak Dinilai/Kosong')
        # Ambil nilai Catatan
        catatan = scores.get(f'catatan_{element_id}', 'Tidak ada catatan khusus.')
        
        display_name = element_id.replace('_', ' ').title()
        
        # Masukkan ke data tabel, gunakan Paragraph untuk word wrap
        final_table_data.append([
            Paragraph(f"<b>{display_name}</b>", styles['Normal']),
            Paragraph(penilaian_ui, styles['Normal']),
            Paragraph(catatan, styles['Normal'])
        ])

    # 4. Buat dan styling tabel
    if final_table_data:
        # Lebar Kolom: Elemen (1.5), Penilaian UI (2.5), Catatan (2.5). Total 6.5 inch
        table_dynamic = Table(final_table_data, colWidths=[1.5*inch, 2.5*inch, 2.5*inch])
        table_dynamic.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkblue), # Header biru gelap
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            
            # Penting: Terapkan word wrap pada kolom 1, 2, dan 3 (indeks 0, 1, 2)
            ('WORDWRAP', (1,1), (1,-1), Paragraph),
            ('WORDWRAP', (2,1), (2,-1), Paragraph),
        ]))
        elements.append(table_dynamic)

    # Membangun PDF
    doc.build(elements)
    return buffer.getvalue()


# ==============================================================================
# 3. ANTARMUKA UTAMA STREAMLIT (Tidak Berubah)
# ==============================================================================

st.header("🤖 Analisis & Penilaian Desain UI Otomatis")

if not client:
    st.error("Gagal menginisialisasi klien Roboflow. Mohon periksa konsol untuk detail error.")
    st.stop()

col1, col2 = st.columns(2)

# Inisialisasi session state untuk path gambar
if 'annotated_image_path' not in st.session_state:
    st.session_state.annotated_image_path = None

with col1:
    st.header("1. Unggah Screenshot")
    uploaded_file = st.file_uploader("Pilih file gambar (PNG, JPG)", type=["png", "jpg", "jpeg"])

    original_image = None
    if uploaded_file is not None:
        original_image = Image.open(uploaded_file)
        st.image(original_image, caption="Gambar Asli yang Diunggah", use_column_width=True)

with col2:
    st.header("2. Hasil Deteksi")
    detection_results = None
    
    # Hapus file sementara lama jika ada unggahan baru
    if uploaded_file is not None and st.session_state.get('last_upload_name') != uploaded_file.name:
         if st.session_state.annotated_image_path and os.path.exists(st.session_state.annotated_image_path):
             os.remove(st.session_state.annotated_image_path)
             st.session_state.annotated_image_path = None
         st.session_state.last_upload_name = uploaded_file.name
         st.session_state.submitted = False # Reset status submit
         st.rerun() # Muat ulang untuk membersihkan state form

    if original_image and COMBINED_MODEL_ID:
        with st.spinner("Sedang menganalisis gambar..."):
            try:
                # Proses prediksi
                temp_input_image_path = "temp_input_image_for_pred.jpeg"
                rgb_image = original_image.convert('RGB')
                rgb_image.save(temp_input_image_path, format='JPEG')
                
                result_dict = client.infer(temp_input_image_path, model_id=COMBINED_MODEL_ID)
                
                os.remove(temp_input_image_path) 

                detection_results = result_dict
                
                annotated_image = draw_annotations(original_image, detection_results['predictions'])
                st.image(annotated_image, caption="Gambar dengan Deteksi Elemen", use_column_width=True)

                # --- Simpan gambar anotasi ke file sementara untuk PDF ---
                annotated_image_path = "temp_annotated_image_for_pdf.jpeg"
                annotated_image.save(annotated_image_path, format='JPEG')
                st.session_state.annotated_image_path = annotated_image_path # Simpan path di session state
                
            except Exception as e:
                st.error(f"Terjadi kesalahan saat prediksi. Pastikan gambar jelas: {e}")
                if os.path.exists(temp_input_image_path):
                    os.remove(temp_input_image_path)
                st.session_state.annotated_image_path = None # Reset path jika gagal
    
    elif uploaded_file:
        st.warning("Menunggu unggahan gambar.")


st.divider()

# ==============================================================================
# 4. FORMULIR PENILAIAN & UNDUH LAPORAN
# ==============================================================================

st.header("3. Formulir Penilaian")

if 'submitted' not in st.session_state:
    st.session_state.submitted = False

if detection_results and 'predictions' in detection_results:
    predictions = detection_results['predictions']
    
    if not predictions:
        st.info("Tidak ada elemen yang terdeteksi pada gambar ini.")
    else:
        st.success(f"Ditemukan **{len(predictions)}** elemen. Silakan isi penilaian.")
        
        with st.form(key="assessment_form"):
            
            # --- Input Bawaan Sistem (Font, Color, Scale) ---
            st.subheader("Penilaian Umum")
            col_font, col_color, col_scale = st.columns(3)
            
            with col_font:
                st.text_area("Font/Tipografi", key="penilaian_font", value=st.session_state.get('penilaian_font', ""), height=100)
            with col_color:
                st.text_area("Warna/Skema", key="penilaian_color", value=st.session_state.get('penilaian_color', ""), height=100)
            with col_scale:
                st.text_area("Skala/Hierarki", key="penilaian_scale", value=st.session_state.get('penilaian_scale', ""), height=100)

            st.divider()
            
            # --- Input Elemen Dinamis ---
            st.subheader("Penilaian Elemen (Berdasarkan Deteksi)")
            element_counts = {} 

            for i, item in enumerate(predictions):
                class_name = item['class']
                
                if class_name not in element_counts:
                    element_counts[class_name] = 0
                element_counts[class_name] += 1
                element_id = f"{class_name}_{element_counts[class_name]}"

                st.markdown(f"**Elemen: {element_id.replace('_', ' ').title()}** (Confidence: {item['confidence']:.2f})")
                
                col_penilaian, col_catatan = st.columns(2)

                with col_penilaian:
                    default_penilaian = st.session_state.get(f"penilaian_{element_id}", "")
                    st.text_area(f"Penilaian UI {element_id}", key=f"penilaian_{element_id}", value=default_penilaian, height=100)
                
                with col_catatan:
                    default_catatan = st.session_state.get(f"catatan_{element_id}", "")
                    st.text_area(f"Catatan Tambahan {element_id}", key=f"catatan_{element_id}", value=default_catatan, height=100)
                
                st.markdown("---")

            submitted = st.form_submit_button("Selesai & Buat Laporan")

            if submitted:
                # Kumpulkan semua data dari form 
                all_scores = {}
                for key, value in st.session_state.items():
                    if key.startswith(("penilaian_", "catatan_", "penilaian_font", "penilaian_color", "penilaian_scale")):
                        all_scores[key] = value

                st.session_state.all_scores = all_scores
                st.session_state.submitted = True
                st.session_state.image_name = uploaded_file.name
                st.success("Penilaian berhasil dikumpulkan. Siap untuk diunduh.")

elif uploaded_file:
    st.info("Menunggu hasil deteksi...")


# --- Unduh Laporan PDF ---
if st.session_state.get('submitted', False) and st.session_state.get('all_scores'):
    
    report_image_path = st.session_state.get('annotated_image_path')
    
    pdf_output = generate_pdf_report(st.session_state.all_scores, report_image_path, st.session_state.image_name)

    st.download_button(
        label="📥 **Unduh Laporan Penilaian UI (PDF)**",
        data=pdf_output,
        file_name=f"Laporan_Penilaian_UI_{os.path.basename(st.session_state.image_name).replace('.', '_')}_{time.strftime('%Y%m%d%H%M%S')}.pdf",
        mime="application/pdf"
    )

    st.info("Tekan tombol di atas untuk mengunduh laporan. Anda dapat mengunggah gambar baru untuk memulai penilaian lain.")
    
    # Hapus file gambar sementara setelah diunduh/tidak lagi diperlukan
    if report_image_path and os.path.exists(report_image_path):
        try:
            os.remove(report_image_path)
            if 'annotated_image_path' in st.session_state:
                del st.session_state['annotated_image_path']
        except OSError as e:
            st.warning(f"Gagal menghapus file sementara: {e}")