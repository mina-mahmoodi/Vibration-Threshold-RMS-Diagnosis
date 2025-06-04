import streamlit as st
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table

# ---- UI: File Upload and Sheet Selection ----

uploaded = st.file_uploader("Upload Excel or CSV files", accept_multiple_files=True)

if uploaded:
    # Dictionary to hold sheet choice for each Excel file
    sheet_choice = {}

    # Identify Excel files and ask user for sheet selection
    for file in uploaded:
        if file.name.endswith(('.xls', '.xlsx')):
            # Read sheets from Excel file
            xls = pd.ExcelFile(file)
            sheets = xls.sheet_names
            sheet = st.selectbox(f"Select sheet for {file.name}", sheets, key=file.name)
            sheet_choice[file.name] = sheet

    # ---- Load and process all datasets ----
    frames = []
    labeled_data = []

    for file in uploaded:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
            label = f"{file.name} (CSV)"
        else:
            sheet = sheet_choice.get(file.name)
            if not sheet:
                st.warning(f"Skipping {file.name} because no sheet selected.")
                continue
            df = pd.read_excel(file, sheet_name=sheet)
            label = f"{file.name} / {sheet}"

        # Check columns
        required_cols = ['T(X)', 'T(Y)', 'T(Z)', 'X', 'Y', 'Z']
        if not all(col in df.columns for col in required_cols):
            st.warning(f"Skipping {label} – missing required columns.")
            continue

        # Convert timestamp columns to datetime
        df[['T(X)', 'T(Y)', 'T(Z)']] = df[['T(X)', 'T(Y)', 'T(Z)']].apply(pd.to_datetime, errors='coerce')
        df = df.dropna(subset=['T(X)', 'T(Y)', 'T(Z)'])

        # Remove zero value rows in X, Y, Z
        df = df[(df[['X', 'Y', 'Z']] != 0).all(axis=1)]

        if df.empty:
            st.warning(f"Skipping {label} – no usable data after filtering.")
            continue

        # Rename columns and select subset
        df_use = df.rename(columns={'T(X)': 't', 'X': 'x', 'Y': 'y', 'Z': 'z'})[['t', 'x', 'y', 'z']]
        frames.append(df_use)
        labeled_data.append((label, df_use))

    if not frames:
        st.error("No usable datasets found.")
        st.stop()

    # Concatenate all data
    data = pd.concat(frames).sort_values('t').reset_index(drop=True)

    # ---- Display dataset coverage info ----
    st.markdown("### Dataset coverage per file/sheet:")
    for label, df_sub in labeled_data:
        st.markdown(f"- **{label}**: {df_sub['t'].min()} → {df_sub['t'].max()} ({len(df_sub):,} rows)")

    st.markdown(f"### Combined dataset coverage:")
    st.markdown(f"From {data['t'].min()} to {data['t'].max()} with total {len(data):,} rows")

    # --- PDF Report Generation Button ---
    if st.button("Generate PDF Report"):

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        flow = []

        flow.append(Paragraph("Vibration Data Report", styles['Title']))
        flow.append(Spacer(1, 12))

        # Dataset sections in PDF
        flow.append(Paragraph("Dataset Sections:", styles['Heading2']))
        for label, df_sub in labeled_data:
            text = f"{label} – {df_sub['t'].min().strftime('%Y-%m-%d %H:%M:%S')} to {df_sub['t'].max().strftime('%Y-%m-%d %H:%M:%S')} " \
                   f"({len(df_sub):,} rows)"
            flow.append(Paragraph(text, styles['Normal']))
        flow.append(Spacer(1, 12))

        # Example threshold table (dummy example, update with your real thresholds)
        threshold_data = [
            ['Parameter', 'Warning Level', 'Error Level'],
            ['x', '0.2', '0.4'],
            ['y', '0.2', '0.4'],
            ['z', '0.2', '0.4']
        ]
        table = Table(threshold_data)
        flow.append(Paragraph("Vibration Thresholds:", styles['Heading2']))
        flow.append(table)
        flow.append(Spacer(1, 12))

        # Add more report content as needed...

        doc.build(flow)
        pdf = buffer.getvalue()
        buffer.close()

        st.download_button(
            label="Download PDF report",
            data=pdf,
            file_name="vibration_report.pdf",
            mime="application/pdf"
        )
