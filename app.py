import pandas as pd
import numpy as np
import streamlit as st

def load_data(uploaded_file):
    return pd.read_excel(uploaded_file)

def filter_vibration_data(df):
    has_motor_state = 'Motor State' in df.columns and 'T(motor state)' in df.columns

    # Ensure all time columns are datetime
    for col in ['T(X)', 'T(Y)', 'T(Z)']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    if has_motor_state:
        df['T(motor state)'] = pd.to_datetime(df['T(motor state)'], errors='coerce')
        # Filter motor ON rows
        df_motor_on = df[df['Motor State'] == 3].copy()
        valid_times = set(df_motor_on['T(motor state)'].dropna())

        # Match timestamps and filter by vibration threshold
        df_filtered = df[
            df['T(X)'].isin(valid_times) &
            df['T(Y)'].isin(valid_times) &
            df['T(Z)'].isin(valid_times) &
            ((df['X'] >= 0.5) | (df['Y'] >= 0.5) | (df['Z'] >= 0.5))
        ].copy()
    else:
        # No motor state info – filter by vibration only
        df_filtered = df[
            (df['X'] >= 0.5) | (df['Y'] >= 0.5) | (df['Z'] >= 0.5)
        ].copy()

    return df_filtered

def calculate_thresholds(df, column):
    warning = df[column].mean() + df[column].std()
    error = df[column].mean() + 2 * df[column].std()
    return warning, error

def diagnose_faults(df, warning_x, error_x, warning_y, error_y, warning_z, error_z):
    df['Fault'] = 'Normal'
    conditions = [
        (df['X'] > error_x) | (df['Y'] > error_y) | (df['Z'] > error_z),
        (df['X'] > warning_x) | (df['Y'] > warning_y) | (df['Z'] > warning_z)
    ]
    choices = ['Severe', 'Moderate']
    df['Fault'] = np.select(conditions, choices, default='Normal')
    return df

# STREAMLIT APP
st.title("CBM - Vibration Threshold & Fault Diagnosis App")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])
if uploaded_file is not None:
    raw_df = load_data(uploaded_file)
    filtered_df = filter_vibration_data(raw_df)

    if not filtered_df.empty:
        # Calculate thresholds
        warning_x, error_x = calculate_thresholds(filtered_df, 'X')
        warning_y, error_y = calculate_thresholds(filtered_df, 'Y')
        warning_z, error_z = calculate_thresholds(filtered_df, 'Z')

        # Fault Diagnosis
        result_df = diagnose_faults(filtered_df, warning_x, error_x, warning_y, error_y, warning_z, error_z)

        st.success("Data filtered and faults diagnosed successfully.")
        st.write("📊 Thresholds:")
        st.write(f"**X** - Warning: {warning_x:.2f}, Error: {error_x:.2f}")
        st.write(f"**Y** - Warning: {warning_y:.2f}, Error: {error_y:.2f}")
        st.write(f"**Z** - Warning: {warning_z:.2f}, Error: {error_z:.2f}")
        st.write("🧾 Diagnosed Data:")
        st.dataframe(result_df)

        # Download
        csv = result_df.to_csv(index=False).encode()
        st.download_button("Download Diagnosed Data as CSV", csv, "diagnosed_data.csv", "text/csv")
    else:
        st.warning("No valid vibration data found after filtering.")
