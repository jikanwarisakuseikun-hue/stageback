import streamlit as st
from PIL import Image
import numpy as np
import os
import csv
import shutil
import pandas as pd
import zipfile

# --- ページ基本設定 ---
st.set_page_config(
    page_title="カスタマイズ可能モザイクアートクリエーター",
    layout="wide"
)

# --- モザイクアート生成ロジック ---

def hex_to_rgb(hex_color):
    """HEXコード(#RRGGBB)をRGBタプルに変換"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def create_mosaic_sheets_from_colors(
    base_image,
    target_colors_data, # [(HEX, 色名), ...]
    total_sheets_vertical,
    total_sheets_horizontal,
    tiles_per_sheet_vertical,
    tiles_per_sheet_horizontal
):
    tile_px_size = 10 # 1タイルあたりの仮想ピクセルサイズ

    mosaic_width_px = total_sheets_horizontal * tiles_per_sheet_horizontal * tile_px_size
    mosaic_height_px = total_sheets_vertical * tiles_per_sheet_vertical * tile_px_size

    base_img = base_image.convert("RGB")
    base_img_resized = base_img.resize((mosaic_width_px, mosaic_height_px), Image.Resampling.LANCZOS)

    target_colors_rgb = [hex_to_rgb(data[0]) for data in target_colors_data]
    target_color_names = [data[1] for data in target_colors_data]

    if not target_colors_rgb:
        raise ValueError("使用する色を少なくとも1つ指定してください。")

    target_colors_np = np.array(target_colors_rgb)
    output_mosaic_img = Image.new("RGB", (mosaic_width_px, mosaic_height_px))

    mosaic_color_names_grid = [
        ['' for _ in range(mosaic_width_px // tile_px_size)]
        for _ in range(mosaic_height_px // tile_px_size)
    ]

    # モザイクアート生成
    tile_row_idx = 0
    for y in range(0, mosaic_height_px, tile_px_size):
        tile_col_idx = 0
        for x in range(0, mosaic_width_px, tile_px_size):
            tile_region = base_img_resized.crop((x, y, x + tile_px_size, y + tile_px_size))
            if tile_region.size[0] == 0 or tile_region.size[1] == 0:
                tile_col_idx += 1
                continue

            tile_avg_color = np.array(tile_region).mean(axis=(0, 1))
            distances = np.linalg.norm(target_colors_np - tile_avg_color, axis=1)
            best_color_index = np.argmin(distances)

            selected_color_rgb = tuple(target_colors_rgb[best_color_index])
            color_tile = Image.new("RGB", (tile_px_size, tile_px_size), selected_color_rgb)
            output_mosaic_img.paste(color_tile, (x, y))

            mosaic_color_names_grid[tile_row_idx][tile_col_idx] = target_color_names[best_color_index]
            tile_col_idx += 1
        tile_row_idx += 1

    # 分割保存とZIP生成
    output_dir = "mosaic_sheets"
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    sheet_width_px = tiles_per_sheet_horizontal * tile_px_size
    sheet_height_px = tiles_per_sheet_vertical * tile_px_size

    individual_sheet_paths = []
    individual_csv_paths = []

    total_mosaic_tiles_vertical = mosaic_height_px // tile_px_size
    total_mosaic_tiles_horizontal = mosaic_width_px // tile_px_size

    for row_sheet_idx in range(total_sheets_vertical):
        for col_sheet_idx in range(total_sheets_horizontal):
            # 画像シート保存
            left_px = col_sheet_idx * sheet_width_px
            top_px = row_sheet_idx * sheet_height_px
            right_px = left_px + sheet_width_px
            bottom_px = top_px + sheet_height_px

            sheet_img = output_mosaic_img.crop((left_px, top_px, right_px, bottom_px))
            sheet_filename = os.path.join(output_dir, f"mosaic_sheet_row{row_sheet_idx+1}_col{col_sheet_idx+1}.png")
            sheet_img.save(sheet_filename)
            individual_sheet_paths.append(sheet_filename)

            # CSVシート保存
            csv_filename = os.path.join(output_dir, f"mosaic_sheet_row{row_sheet_idx+1}_col{col_sheet_idx+1}_colors.csv")
            individual_csv_paths.append(csv_filename)

            start_tile_row = row_sheet_idx * tiles_per_sheet_vertical
            end_tile_row = min(start_tile_row + tiles_per_sheet_vertical, total_mosaic_tiles_vertical)
            start_tile_col = col_sheet_idx * tiles_per_sheet_horizontal
            end_tile_col = min(start_tile_col + tiles_per_sheet_horizontal, total_mosaic_tiles_horizontal)

            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                csv_writer = csv.writer(csvfile)
                header = ["行/列"] + [f"列{j+1}" for j in range(end_tile_col - start_tile_col)]
                csv_writer.writerow(header)

                for r in range(start_tile_row, end_tile_row):
                    row_data = [f"行{r - start_tile_row + 1}"]
                    for c in range(start_tile_col, end_tile_col):
                        row_data.append(mosaic_color_names_grid[r][c])
                    csv_writer.writerow(row_data)

    # ZIP作成
    images_zip_path = os.path.join(output_dir, "mosaic_sheets_images.zip")
    with zipfile.ZipFile(images_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in individual_sheet_paths:
            zipf.write(file_path, os.path.basename(file_path))

    csvs_zip_path = os.path.join(output_dir, "mosaic_sheets_csvs.zip")
    with zipfile.ZipFile(csvs_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in individual_csv_paths:
            zipf.write(file_path, os.path.basename(file_path))

    return output_mosaic_img, individual_sheet_paths, individual_csv_paths, images_zip_path, csvs_zip_path


# --- Streamlit UI構築 ---

st.title("🧩 カスタマイズ可能モザイクアートクリエーター")
st.markdown("""
元画像をアップロードし、使用する色・シート分割数・タイル数を設定してモザイクアートと色指示CSVを生成します。
生成された全画像と全CSVは、それぞれZIPファイルとして一括ダウンロードできます。
""")

# サイドバーまたはカラムで入力項目を配置
col_input, col_config = st.columns([1, 1])

with col_input:
    st.subheader("1. 画像と色の設定")
    uploaded_file = st.file_uploader("ベース画像をアップロード", type=["png", "jpg", "jpeg"])

    num_colors = st.slider("使用する色の数", min_value=2, max_value=20, value=5)

    target_colors_data = []
    st.markdown("**各色のカラーピッカーと名前**")
    
    # 動的にカラーピッカーとテキストボックスを生成
    default_hexes = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF", "#000000", "#FFFFFF"]
    default_names = ["赤", "緑", "青", "黄", "マゼンタ", "シアン", "黒", "白"]

    for i in range(num_colors):
        c1, c2 = st.columns([1, 2])
        hex_val = default_hexes[i % len(default_hexes)]
        name_val = default_names[i % len(default_names)] if i < len(default_names) else f"色{i+1}"
        
        with c1:
            color = st.color_picker(f"色 {i+1}", hex_val, key=f"color_{i}")
        with c2:
            color_name = st.text_input(f"色 {i+1} の名前", name_val, key=f"name_{i}")
        
        target_colors_data.append((color, color_name))

with col_config:
    st.subheader("2. モザイクアートのサイズ設定")
    total_sheets_vertical = st.slider("モザイクアート全体の縦のシート枚数", 1, 20, 8)
    total_sheets_horizontal = st.slider("モザイクアート全体の横のシート枚数", 1, 20, 12)
    tiles_per_sheet_vertical = st.slider("1枚のシートあたりのタイルの縦の数", 5, 50, 10)
    tiles_per_sheet_horizontal = st.slider("1枚のシートあたりのタイルの横の数", 5, 50, 10)

st.markdown("---")

# 生成ボタン
if st.button("🚀 モザイクアートを生成", type="primary", use_container_width=True):
    if uploaded_file is None:
        st.error("ベース画像をアップロードしてください。")
    elif any(not name.strip() for _, name in target_colors_data):
        st.warning("すべての色の名前を入力してください。")
    else:
        with st.spinner("モザイクアートを生成中..."):
            try:
                base_image = Image.open(uploaded_file)
                
                full_mosaic, img_paths, csv_paths, img_zip, csv_zip = create_mosaic_sheets_from_colors(
                    base_image=base_image,
                    target_colors_data=target_colors_data,
                    total_sheets_vertical=total_sheets_vertical,
                    total_sheets_horizontal=total_sheets_horizontal,
                    tiles_per_sheet_vertical=tiles_per_sheet_vertical,
                    tiles_per_sheet_horizontal=tiles_per_sheet_horizontal
                )

                # セッション状態に結果を保存（再描画時の消失防止）
                st.session_state["full_mosaic"] = full_mosaic
                st.session_state["img_zip"] = img_zip
                st.session_state["csv_zip"] = csv_zip
                st.session_state["csv_paths"] = csv_paths
                st.success("モザイクアートが生成されました！")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

# 結果表示エリア
if "full_mosaic" in st.session_state:
    st.subheader("🖼️ 生成結果")
    st.image(st.session_state["full_mosaic"], caption="モザイクアート全体像", use_column_width=True)

    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        with open(st.session_state["img_zip"], "rb") as f:
            st.download_button(
                label="📦 全てのシート画像をZIPでダウンロード",
                data=f,
                file_name="mosaic_sheets_images.zip",
                mime="application/zip",
                use_container_width=True
            )

    with col_dl2:
        with open(st.session_state["csv_zip"], "rb") as f:
            st.download_button(
                label="📄 全てのCSV色指示書をZIPでダウンロード",
                data=f,
                file_name="mosaic_sheets_csvs.zip",
                mime="application/zip",
                use_container_width=True
            )

    st.markdown("---")
    st.subheader("📊 各シートの色指示表プレビュー")
    
    csv_paths = st.session_state["csv_paths"]
    csv_names = [os.path.basename(p) for p in csv_paths]
    selected_csv_name = st.selectbox("表示するシートのCSVを選択", csv_names)

    if selected_csv_name:
        selected_path = next(p for p in csv_paths if os.path.basename(p) == selected_csv_name)
        df = pd.read_csv(selected_path)
        st.dataframe(df, use_container_width=True)
