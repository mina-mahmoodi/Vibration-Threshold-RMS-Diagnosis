import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.express as px
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                Table, TableStyle, Image)

# ──────────────────────────────────────────────────────────────
# Page & title
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="📊 Vibration Threshold & RMS Diagnosis", layout="wide")
st.title("📊 Vibration Threshold & RMS-Based Fault Diagnosis")

# ──────────────────────────────────────────────────────────────
# Upload / sheet selection
# ──────────────────────────────────────────────────────────────
uploaded = st.file_uploader("📂 Upload one or more vibration files", type=["csv", "xlsx"],
                            accept_multiple_files=True)

if uploaded:
    sheet_choice = {}
    for file in uploaded:
        if file.name.endswith(".csv"):
            sheet_choice[file.name] = "CSV Data"
        else:
            try:
                xls = pd.ExcelFile(file)
                sheet_choice[file.name] = st.selectbox(
                    f"Select sheet from {file.name}",
                    ["-- Select a sheet --"] + xls.sheet_names,
                    key=file.name
                )
            except Exception as e:
                st.error(f"Error reading {file.name}: {e}")

    if not all(val and val != "-- Select a sheet --" for val in sheet_choice.values()):
        st.info("📑 Please choose a sheet for every uploaded Excel.")
        st.stop()

    # ──────────────────────────────────────────────────────────
    # Load & merge
    # ──────────────────────────────────────────────────────────
    frames = []
    for file in uploaded:
        sheet = sheet_choice[file.name]
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file, sheet_name=sheet)

        if not all(col in df.columns for col in ['T(X)', 'T(Y)', 'T(Z)', 'X', 'Y', 'Z']):
            st.warning(f"Skipping {file.name}/{sheet} (columns missing).")
            continue

        # Timestamp → datetime
        df[['T(X)', 'T(Y)', 'T(Z)']] = df[['T(X)', 'T(Y)', 'T(Z)']].apply(
            pd.to_datetime, errors='coerce')
        df = df.dropna(subset=['T(X)', 'T(Y)', 'T(Z)'])
        df = df[(df[['X', 'Y', 'Z']] != 0).all(axis=1)]  # drop all-zero rows

        if df.empty:
            st.warning(f"Skipping {file.name}/{sheet} – no usable rows.")
            continue

        # standardise column names
        df_use = df.rename(columns={'T(X)':'t', 'X':'x', 'Y':'y', 'Z':'z'})[['t','x','y','z']]
        frames.append(df_use)

    if not frames:
        st.error("❌ No usable data after filtering.")
        st.stop()

    data = pd.concat(frames).sort_values('t').reset_index(drop=True)

    st.markdown(f"**Dataset coverage:** {data['t'].min()} → {data['t'].max()} "
                f"({len(data):,} rows)")

    # ──────────────────────────────────────────────────────────
    # Percentile thresholds
    # ──────────────────────────────────────────────────────────
    percentiles = {
        axis: {
            "warning": math.ceil(data[axis].quantile(0.85)*100)/100,
            "error":   math.ceil(data[axis].quantile(0.95)*100)/100
        } for axis in ['x','y','z']
    }

    st.subheader("🎯 85th / 95th-Percentile Thresholds")
    thr_tbl = pd.DataFrame([
        dict(Axis=a.upper(), **vals) for a, vals in percentiles.items()
    ])
    thr_cols = st.columns(3)
    for i, axis in enumerate(['x','y','z']):
        thr_cols[i].metric(f"{axis.upper()} 85 % warn", f"{percentiles[axis]['warning']:.2f}")
        thr_cols[i].metric(f"{axis.upper()} 95 % error", f"{percentiles[axis]['error']:.2f}")

    # ──────────────────────────────────────────────────────────
    # Axis selection & plotting
    # ──────────────────────────────────────────────────────────
    plot_axis = st.selectbox("📌 Axis to plot", ['x','y','z'], index=0)

    plot_df = data.iloc[::max(1, len(data)//5000)]   # down-sample if huge
    fig = px.line(plot_df, x='t', y=plot_axis,
                  title=f"{plot_axis.upper()} vibration with thresholds",
                  labels={'t':'Timestamp', plot_axis: f"{plot_axis.upper()} amplitude"})
    fig.add_hline(percentiles[plot_axis]['warning'], line_dash='dash', line_color='orange',
                  annotation_text="85 % warn", annotation_position="top left")
    fig.add_hline(percentiles[plot_axis]['error'], line_dash='dot', line_color='red',
                  annotation_text="95 % error", annotation_position="top left")
    st.plotly_chart(fig, use_container_width=True)

    # ──────────────────────────────────────────────────────────
    # RMS calculation (fixed 10-sample window) & diagnosis
    # ──────────────────────────────────────────────────────────
    win = 10
    diag_df = data.copy()
    for axis in ['x','y','z']:
        diag_df[f'{axis}_rms'] = diag_df[axis].rolling(win, min_periods=1)\
                                             .apply(lambda v: np.sqrt(np.mean(v**2)), raw=True)

    def judge(row):
        notes=[]
        if row['x_rms']>percentiles['x']['warning'] or row['y_rms']>percentiles['y']['warning']:
            notes.append("🔧 Radial RMS ≥ 85 % (possible unbalance/misalignment)")
        if row['z_rms']>percentiles['z']['warning']:
            notes.append("📏 Axial RMS ≥ 85 % (possible axial load/misalignment)")
        if abs(row['x_rms']-row['y_rms'])>0.2:
            notes.append("🔩 |X-Y| > 0.2 (possible looseness)")
        return "✅ Normal" if not notes else "; ".join(notes)

    diag_df['Diagnosis'] = diag_df.apply(judge, axis=1)

    st.subheader("📋 Last 50 diagnosed rows")
    st.dataframe(diag_df[['t','x_rms','y_rms','z_rms','Diagnosis']].tail(50))

    # ──────────────────────────────────────────────────────────
    # PDF generation (threshold table + plot + diagnosis table)
    # ──────────────────────────────────────────────────────────
    if st.button("📄 Generate PDF Report"):
        # save plot to bytes
        plot_bytes = fig.to_image(format="png")

        pdf_buf = BytesIO()
        doc = SimpleDocTemplate(pdf_buf, pagesize=letter)
        styles = getSampleStyleSheet()
        flow = []

        flow.append(Paragraph("Vibration Threshold and RMS Diagnosis Report",
                              styles['Title']))
        flow.append(Spacer(1,12))

        # explanation
        flow.append(Paragraph(
            "<b>Diagnosis logic</b><br/>"
            "- RMS ≥ 85th-percentile triggers <i>warning</i>; "
            "RMS ≥ 95th triggers <i>error</i>.<br/>"
            "- Radial high values → possible <i>unbalance/misalignment</i>.<br/>"
            "- Axial high values → possible <i>axial load/misalignment</i>.<br/>"
            "- |X-RMS – Y-RMS| > 0.2 g → possible <i>looseness</i>.",
            styles['Normal']))
        flow.append(Spacer(1,12))

        # thresholds table
        tbl_data=[["Axis","85 % Warn","95 % Error"]]
        for ax in ['x','y','z']:
            tbl_data.append([ax.upper(),
                             f"{percentiles[ax]['warning']:.2f}",
                             f"{percentiles[ax]['error']:.2f}"])
        tbl = Table(tbl_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.grey),
            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold')
        ]))
        flow.append(tbl)
        flow.append(Spacer(1,12))

        # embed plot image
        img = Image(BytesIO(plot_bytes))
        img.drawHeight = 4*72   # 4 inches
        img.drawWidth  = 6*72   # 6 inches
        flow.append(img)
        flow.append(Spacer(1,12))

        # last 20 diagnosis rows in a table
        diag_rows = diag_df[['t','x_rms','y_rms','z_rms','Diagnosis']].tail(20)
        pdf_table = [['Time','X RMS','Y RMS','Z RMS','Diagnosis']]
        for _,r in diag_rows.iterrows():
            pdf_table.append([r['t'].strftime('%Y-%m-%d %H:%M:%S'),
                              f"{r['x_rms']:.3f}",
                              f"{r['y_rms']:.3f}",
                              f"{r['z_rms']:.3f}",
                              r['Diagnosis']])
        dtbl = Table(pdf_table, repeatRows=1, colWidths=[85,45,45,45,210])
        dtbl.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.grey),
            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
            ('GRID',(0,0),(-1,-1),0.3,colors.grey),
            ('ALIGN',(1,1),(-2,-1),'RIGHT'),
            ('FONTSIZE',(0,0),(-1,-1),7)
        ]))
        flow.append(dtbl)

        doc.build(flow)
        pdf_buf.seek(0)

        st.download_button("⬇️ Download PDF Report",
                           data=pdf_buf,
                           file_name="vibration_report.pdf",
                           mime="application/pdf")
else:
    st.info("⬆️ Upload CSV or Excel files to begin.")
