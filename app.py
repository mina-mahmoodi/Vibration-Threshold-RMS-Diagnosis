import streamlit as st
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table

# ---- Upload section ----
uploaded = st.file_uploader("Upload Excel or CSV files", accept_multiple_files=True)

if uploaded:
    sheet_choice = {}
    excel_files = [f for f in uploaded if f.name.endswith(('.xls', '.xlsx'))]

    # Sheet selection UI
    for file in excel_files:
        xls = pd.ExcelFile(file)
        sheets = xls.sheet_names
        selected = st.selectbox(f"Select a sheet from {file.name}", sheets, key=file.name)
        sheet_choice[file.name] = selected

    # ---- Read all data ----
    frames = []
    labeled_data = []

    for file in uploaded:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
            label = f"{file.name} (CSV)"
        else:
            sheet = sheet_choice.get(file.name)
            if not sheet:
                continue
            df = pd.read_excel(file, sheet_name=sheet)
            label = f"{file.name} / {sheet}"

        # Check columns
        required = ['T(X)', 'T(Y)', 'T(Z)', 'X', 'Y', 'Z']
        if not all(col in df.columns for col in required):
            st.warning(f"{label}: Missing required columns, skipped.")
            continue

        # Convert to datetime
        df[['T(X)', 'T(Y)', 'T(Z)']] = df[['T(X)', 'T(Y)', 'T(Z)']].apply(pd.to_datetime, errors='coerce')
        df = df.dropna(subset=['T(X)', 'T(Y)', 'T(Z)'])

        # Remove zero rows
        df = df[(df[['X', 'Y', 'Z']] != 0).all(axis=1)]

        if df.empty:
            st.warning(f"{label}: No usable data after filtering, skipped.")
            continue

        df_use = df.rename(columns={'T(X)': 't', 'X': 'x', 'Y': 'y', 'Z': 'z'})[['t', 'x', 'y', 'z']]
        frames.append(df_use)
        labeled_data.append((label, df_use))

    if not frames:
        st.error("No valid data found.")
        st.stop()

    # Combine and sort
    combined = pd.concat(frames).sort_values('t').reset_index(drop=True)

    # ---- Show details on page ----
    st.markdown("### Data Coverage by File/Sheet")
    for label, df_part in labeled_data:
        st.markdown(f"- **{label}**: {df_part['t'].min()} → {df_part['t'].max()} ({len(df_part):,} rows)")

    st.markdown(f"### Combined Dataset:")
    st.markdown(f"From **{combined['t'].min()}** to **{combined['t'].max()}** with **{len(combined):,} rows**")

    # ---- Generate PDF Report ----
    if st.button("Generate PDF Report"):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        flow = []

        flow.append(Paragraph("Vibration Data Report", styles['Title']))
        flow.append(Spacer(1, 12))

        # Data section
        flow.append(Paragraph("Dataset Summary", styles['Heading2']))
        for label, df_part in labeled_data:
            text = f"{label}: {df_part['t'].min().strftime('%Y-%m-%d %H:%M:%S')} → " \
                   f"{df_part['t'].max().strftime('%Y-%m-%d %H:%M:%S')} ({len(df_part):,} rows)"
            flow.append(Paragraph(text, styles['Normal']))
        flow.append(Spacer(1, 12))

        # Example: Threshold table
        table_data = [
            ['Parameter', 'Warning', 'Error'],
            ['x', '0.2', '0.4'],
            ['y', '0.2', '0.4'],
            ['z', '0.2', '0.4']
        ]
        table = Table(table_data)
        flow.append(Paragraph("Thresholds", styles['Heading2']))
        flow.append(table)

        doc.build(flow)
        pdf = buffer.getvalue()
        buffer.close()

        st.download_button("Download Report as PDF", data=pdf, file_name="vibration_report.pdf", mime="application/pdf")
