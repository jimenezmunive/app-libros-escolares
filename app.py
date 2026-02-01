import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestión Libros Escolares", layout="wide", page_icon="📚")

# --- NOMBRES DE ARCHIVOS ---
FILE_INVENTARIO = 'inventario.csv'
FILE_PEDIDOS = 'base_datos_pedidos.csv'

# --- FUNCIONES DE CARGA Y GUARDADO ---
def cargar_inventario():
    if os.path.exists(FILE_INVENTARIO):
        return pd.read_csv(FILE_INVENTARIO)
    else:
        return pd.DataFrame(columns=["Grado", "Area", "Libro", "Costo", "Precio Venta", "Ganancia"])

def guardar_inventario(df):
    for col in ['Costo', 'Precio Venta']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Ganancia'] = df['Precio Venta'] - df['Costo']
    df.to_csv(FILE_INVENTARIO, index=False)

def cargar_pedidos():
    if os.path.exists(FILE_PEDIDOS):
        return pd.read_csv(FILE_PEDIDOS)
    else:
        return pd.DataFrame(columns=[
            "ID_Pedido", "Fecha_Creacion", "Ultima_Modificacion", "Cliente", "Celular", 
            "Detalle", "Total", "Abonado", "Saldo", "Estado", "Comprobante", "Historial_Cambios"
        ])

def guardar_pedido_db(df):
    df.to_csv(FILE_PEDIDOS, index=False)

# --- FUNCIÓN GENERAR LINK WHATSAPP ---
def generar_link_whatsapp(celular, mensaje):
    celular = str(celular).replace(" ", "").replace("+", "").strip()
    if not celular.startswith("57"): 
        celular = "57" + celular
    texto_codificado = mensaje.replace(" ", "%20").replace("\n", "%0A")
    return f"https://wa.me/{celular}?text={texto_codificado}"

# --- FUNCIÓN GENERADOR EXCEL MATRIZ (PACKING LIST) ---
def generar_excel_matriz_bytes(df_pedidos, df_inventario):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    worksheet = workbook.add_worksheet("Listado Matriz")
    
    # Formatos
    fmt_header_grado = workbook.add_format({'bold': True, 'font_size': 14, 'bg_color': '#DDEBF7', 'border': 1})
    fmt_col_header = workbook.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
    fmt_cell = workbook.add_format({'border': 1, 'align': 'center'})
    fmt_cell_text = workbook.add_format({'border': 1, 'align': 'left'})
    fmt_money = workbook.add_format({'border': 1, 'num_format': '$#,##0', 'align': 'right'})
    fmt_total_row = workbook.add_format({'bold': True, 'bg_color': '#E2EFDA', 'border': 1, 'align': 'center'})

    current_row = 0
    grados_ordenados = df_inventario['Grado'].unique() # Asumimos orden de carga o alfabético

    for grado in grados_ordenados:
        # 1. Filtrar inventario de este grado
        inv_grado = df_inventario[df_inventario['Grado'] == grado]
        if inv_grado.empty: continue
        
        # Mapeo: Libro -> Area (para poner Area en el encabezado)
        mapa_libro_area = dict(zip(inv_grado['Libro'], inv_grado['Area']))
        areas_unicas = inv_grado['Area'].unique() # Columnas de la matriz
        
        # 2. Filtrar pedidos que contengan este grado
        # Buscamos en el string 'Detalle' si contiene "[GRADO]"
        patron_grado = f"[{grado}]"
        pedidos_grado = df_pedidos[df_pedidos['Detalle'].str.contains(patron_grado, regex=False, na=False)].copy()
        
        if pedidos_grado.empty:
            continue # Si no hay pedidos para este grado, saltamos

        # 3. Construir la Matriz de Datos
        data_rows = []
        for idx, pedido in pedidos_grado.iterrows():
            row_dict = {
                'Cliente': pedido['Cliente'],
                'Celular': pedido['Celular'],
                'Saldo': pedido['Saldo']
            }
            # Inicializar áreas en 0
            for area in areas_unicas:
                row_dict[area] = 0
            
            # Parsear Detalle
            items = str(pedido['Detalle']).split(" | ")
            libros_comprados_count = 0
            
            for item in items:
                # item ej: "[PRIMERO] MATEMATICAS"
                if patron_grado in item:
                    # Extraer nombre libro: quitar "[PRIMERO] "
                    nombre_libro = item.replace(patron_grado, "").strip()
                    # Buscar su area
                    area_correspondiente = mapa_libro_area.get(nombre_libro)
                    if area_correspondiente:
                        row_dict[area_correspondiente] = 1
                        libros_comprados_count += 1
            
            row_dict['Total Libros'] = libros_comprados_count
            data_rows.append(row_dict)

        if not data_rows: continue

        # 4. Escribir en Excel
        
        # A) Título del Grado
        worksheet.merge_range(current_row, 0, current_row, 3 + len(areas_unicas), f"GRADO: {grado}", fmt_header_grado)
        current_row += 1
        
        # B) Encabezados de Columna
        headers = ['Cliente', 'Celular', 'Saldo'] + list(areas_unicas) + ['Total Libros']
        for col_num, header in enumerate(headers):
            worksheet.write(current_row, col_num, header, fmt_col_header)
            # Ajustar ancho
            if header == 'Cliente': worksheet.set_column(col_num, col_num, 30)
            elif header == 'Celular': worksheet.set_column(col_num, col_num, 15)
            else: worksheet.set_column(col_num, col_num, 12)
        current_row += 1
        
        # C) Filas de Datos
        # Calcular totales verticales
        totales_verticales = {area: 0 for area in areas_unicas}
        totales_verticales['Total Libros'] = 0

        for row_data in data_rows:
            # Cliente
            worksheet.write(current_row, 0, row_data['Cliente'], fmt_cell_text)
            worksheet.write(current_row, 1, row_data['Celular'], fmt_cell)
            worksheet.write(current_row, 2, row_data['Saldo'], fmt_money)
            
            # Areas (1 o 0)
            col_idx = 3
            for area in areas_unicas:
                val = row_data[area]
                worksheet.write(current_row, col_idx, val if val > 0 else "", fmt_cell) # Dejar vacío si es 0 para limpieza visual
                totales_verticales[area] += val
                col_idx += 1
            
            # Total Fila
            worksheet.write(current_row, col_idx, row_data['Total Libros'], fmt_cell)
            totales_verticales['Total Libros'] += row_data['Total Libros']
            
            current_row += 1
            
        # D) Fila de Totales del Grado
        worksheet.write(current_row, 0, "TOTALES GRADO", fmt_total_row)
        worksheet.write(current_row, 1, "", fmt_total_row)
        worksheet.write(current_row, 2, "", fmt_total_row)
        
        col_idx = 3
        for area in areas_unicas:
            worksheet.write(current_row, col_idx, totales_verticales[area], fmt_total_row)
            col_idx += 1
        worksheet.write(current_row, col_idx, totales_verticales['Total Libros'], fmt_total_row)
        
        # Espacio para el siguiente bloque
        current_row += 3 

    writer.close()
    return output

# --- COMPONENTE DE SELECCIÓN DE LIBROS ---
def componente_seleccion_libros(inventario, key_suffix, seleccion_previa=None):
    grados = inventario['Grado'].unique()
    seleccion_final = []
    total_final = 0
    
    for grado in grados:
        df_grado = inventario[inventario['Grado'] == grado]
        
        with st.expander(f"{grado}"):
            items_grado_individuales = []
            valor_grado_individuales = 0
            
            for index, row in df_grado.iterrows():
                key_check = f"{grado}_{row['Area']}_{row['Libro']}_{key_suffix}"
                label = f"{row['Area']} - {row['Libro']} (${int(row['Precio Venta']):,})"
                
                checked = False
                if seleccion_previa and f"[{grado}] {row['Libro']}" in seleccion_previa:
                    checked = True
                
                if st.checkbox(label, key=key_check, value=checked):
                    items_grado_individuales.append(f"[{grado}] {row['Libro']}")
                    valor_grado_individuales += row['Precio Venta']
            
            st.divider() 
            
            check_todos = st.checkbox(f"Seleccionar TODOS los de {grado}", key=f"all_{grado}_{key_suffix}")
            
            if check_todos:
                for index, row in df_grado.iterrows():
                    seleccion_final.append(f"[{grado}] {row['Libro']}")
                    total_final += row['Precio Venta']
            else:
                seleccion_final.extend(items_grado_individuales)
                total_final += valor_grado_individuales

    return seleccion_final, total_final

# --- VISTA 1: CLIENTE (PÚBLICA) ---
def vista_cliente(pedido_id=None):
    st.image("https://cdn-icons-png.flaticon.com/512/2232/2232688.png", width=60)
    st.title("📚 Formulario de Pedido")
    st.caption("No requiere usuario ni contraseña.")
    
    inventario = cargar_inventario()
    if inventario.empty:
        st.error("El sistema no tiene libros cargados.")
        return

    datos_previos = {}
    es_modificacion = False
    
    if pedido_id:
        df_pedidos = cargar_pedidos()
        pedido_existente = df_pedidos[df_pedidos['ID_Pedido'] == pedido_id]
        if not pedido_existente.empty:
            datos_previos = pedido_existente.iloc[0].to_dict()
            es_modificacion = True
            st.info(f"📝 Modificando pedido: {datos_previos['ID_Pedido']}")

    with st.form("form_cliente"):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre Completo", value=datos_previos.get('Cliente', ''))
        celular = c2.text_input("Celular", value=datos_previos.get('Celular', ''))

        st.divider()
        st.subheader("Seleccionar Pedido:") 
        items, total = componente_seleccion_libros(inventario, "cli", datos_previos.get('Detalle', ''))
        
        st.divider()
        st.metric("Total a Pagar", f"${total:,.0f}")
        
        st.subheader("Pago")
        # MODIFICACIÓN: SOLO 2 OPCIONES
        tipo = st.radio("Método:", ["Pago Total", "Abono Parcial"], horizontal=True)
        
        abono = st.number_input("Valor a transferir hoy:", min_value=0.0, step=1000.0, value=float(datos_previos.get('Abonado', 0)))
        archivo = st.file_uploader("Comprobante (Imagen/PDF)", type=['jpg','png','jpeg','pdf'])

        if st.form_submit_button("✅ ENVIAR PEDIDO"):
            if not nombre or not celular:
                st.error("Falta Nombre o Celular")
            elif total == 0:
                st.error("Seleccione libros")
            elif abono == 0:
                 st.error("Por favor ingrese el valor del abono o pago.")
            elif not archivo and not es_modificacion:
                 st.error("Por favor adjunte el comprobante de pago.")
            else:
                df = cargar_pedidos()
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                saldo = total - abono
                
                if es_modificacion:
                    idx = df[df['ID_Pedido'] == pedido_id].index[0]
                    df.at[idx, 'Ultima_Modificacion'] = fecha
                    df.at[idx, 'Detalle'] = " | ".join(items)
                    df.at[idx, 'Total'] = total
                    df.at[idx, 'Abonado'] = abono
                    df.at[idx, 'Saldo'] = saldo
                    if archivo: df.at[idx, 'Comprobante'] = "Nuevo Comprobante"
                    df.at[idx, 'Historial_Cambios'] += f" | Modif: {fecha}"
                    st.success("Pedido Actualizado")
                else:
                    nuevo_id = str(uuid.uuid4())[:8]
                    nuevo = {
                        "ID_Pedido": nuevo_id, "Fecha_Creacion": fecha, "Ultima_Modificacion": fecha,
                        "Cliente": nombre, "Celular": celular, "Detalle": " | ".join(items),
                        "Total": total, "Abonado": abono, "Saldo": saldo, "Estado": "Nuevo",
                        "Comprobante": "Si" if archivo else "No", "Historial_Cambios": "Original"
                    }
                    df = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
                    st.success(f"Pedido Creado! ID: {nuevo_id}")
                    st.balloons()
                guardar_pedido_db(df)

# --- VISTA 2: ADMINISTRADOR ---
def vista_admin():
    st.sidebar.header("⚙️ Configuración Link")
    url_app = st.sidebar.text_input("LINK App Publicada:", 
                                    value="https://tu-app.streamlit.app", 
                                    help="Pega aquí el link de internet de tu app.")
    
    menu = st.sidebar.radio("Navegación:", ["📊 Panel de Ventas", "📦 Inventario de Libros"])

    # ---------------- SECCIÓN 1: INVENTARIO ----------------
    if menu == "📦 Inventario de Libros":
        st.title("📦 Inventario de Libros")
        
        with st.expander("Subir Excel Masivo"):
            up = st.file_uploader("Excel (Grado, Area, Libro, Costo, Precio Venta)", type=['xlsx','csv'])
            if up:
                try:
                    df_up = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
                    guardar_inventario(df_up)
                    st.success("Cargado!")
                except: st.error("Error en archivo")
        
        df = cargar_inventario()
        if not df.empty:
            df_ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
            if st.button("Guardar Inventario"):
                guardar_inventario(df_ed)
                st.rerun()
            
            st.write("---")
            st.subheader("Resumen Financiero por Grado")
            resumen = df.groupby("Grado")[["Costo", "Precio Venta", "Ganancia"]].sum().reset_index()
            st.dataframe(resumen, use_container_width=True)

    # ---------------- SECCIÓN 2: PANEL DE VENTAS ----------------
    elif menu == "📊 Panel de Ventas":
        st.title("📊 Panel de Ventas")
        df_pedidos = cargar_pedidos()

        # A) HERRAMIENTAS WHATSAPP
        st.container(border=True)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📲 Enviar WhatsApp")
            tel = st.text_input("Celular Cliente:", key="tel_wa")
            if tel:
                if "tu-app" in url_app or "localhost" in url_app:
                    st.warning("⚠️ Recuerda pegar el LINK REAL en el menú izquierdo.")
                link_ped = f"{url_app}?rol=cliente"
                msg = f"Hola, haz tu pedido aquí: {link_ped}"
                link_wa = generar_link_whatsapp(tel, msg)
                st.link_button("Enviar Mensaje", link_wa)
        with c2:
            st.subheader("🔗 Copiar Link General")
            st.code(f"{url_app}?rol=cliente", language="text")

        st.divider()

        # B) INGRESO MANUAL
        with st.expander("➕ Registrar Nuevo Pedido Manualmente (Presencial / Telefónico)", expanded=False):
            st.markdown("##### Formulario de Ingreso Manual")
            inventario = cargar_inventario()
            
            if inventario.empty:
                st.warning("⚠️ No hay inventario cargado.")
            else:
                with st.form("form_manual_admin"):
                    mc1, mc2 = st.columns(2)
                    m_nombre = mc1.text_input("Nombre Cliente")
                    m_celular = mc2.text_input("Celular")
                    
                    st.write("**Seleccionar Pedido:**")
                    m_items, m_total = componente_seleccion_libros(inventario, "adm")
                    
                    st.write("---")
                    col_tot, col_abo = st.columns(2)
                    col_tot.metric("Total Pedido", f"${m_total:,.0f}")
                    m_abono = col_abo.number_input("Abono Recibido ($):", min_value=0.0, step=1000.0)
                    
                    m_estado = st.selectbox("Estado del Pedido:", ["Nuevo", "Pagado Total", "Entregado Inmediato"])

                    if st.form_submit_button("💾 GUARDAR PEDIDO MANUAL"):
                        if not m_nombre:
                            st.error("Falta Nombre")
                        elif m_total == 0:
                            st.error("Faltan Libros")
                        else:
                            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            nuevo_id = str(uuid.uuid4())[:8]
                            nuevo_p = {
                                "ID_Pedido": nuevo_id, "Fecha_Creacion": fecha, "Ultima_Modificacion": fecha,
                                "Cliente": m_nombre, "Celular": m_celular, "Detalle": " | ".join(m_items),
                                "Total": m_total, "Abonado": m_abono, "Saldo": m_total - m_abono, "Estado": m_estado,
                                "Comprobante": "Manual/Presencial", "Historial_Cambios": "Creado por Admin (Manual)"
                            }
                            df_new = pd.DataFrame([nuevo_p])
                            df_pedidos = pd.concat([df_pedidos, df_new], ignore_index=True)
                            guardar_pedido_db(df_pedidos)
                            st.success(f"✅ Pedido guardado exitosamente!")
                            st.rerun()

        st.divider()

        # C) LISTADO DE PEDIDOS Y EXPORTACIÓN MATRIZ
        col_title, col_btn = st.columns([3, 1])
        with col_title:
            st.subheader("📋 Listado de Pedidos")
        with col_btn:
            # BOTÓN DE DESCARGA EXCEL (MATRIZ / PACKING LIST)
            if not df_pedidos.empty:
                inventario_actual = cargar_inventario()
                if not inventario_actual.empty:
                    excel_bytes = generar_excel_matriz_bytes(df_pedidos, inventario_actual)
                    
                    st.download_button(
                        label="📥 Descargar Reporte Matriz (Excel)",
                        data=excel_bytes,
                        file_name="Reporte_Pedidos_Matriz.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Carga el inventario para generar el reporte.")
        
        if not df_pedidos.empty:
            filtro = st.text_input("🔍 Buscar Pedido (Nombre/Celular):")
            if filtro:
                df_view = df_pedidos[df_pedidos['Cliente'].str.contains(filtro, case=False, na=False)]
            else:
                df_view = df_pedidos

            edited = st.data_editor(
                df_view,
                column_config={
                    "Estado": st.column_config.SelectboxColumn(options=["Nuevo", "Pagado", "En Impresión", "Entregado", "Anulado"], required=True),
                    "Total": st.column_config.NumberColumn(format="$%d"),
                    "Saldo": st.column_config.NumberColumn(format="$%d")
                },
                disabled=["ID_Pedido", "Detalle"],
                hide_index=True
            )
            if st.button("💾 Actualizar Estados en Tabla"):
                df_pedidos.update(edited)
                guardar_pedido_db(df_pedidos)
                st.success("Cambios guardados.")
            
            st.write("---")
            st.caption("Herramientas de Edición:")
            p_sel = st.selectbox("Seleccionar Pedido para Editar/Reenviar:", df_pedidos['ID_Pedido'] + " - " + df_pedidos['Cliente'])
            if p_sel:
                id_sel = p_sel.split(" - ")[0]
                fila = df_pedidos[df_pedidos['ID_Pedido'] == id_sel].iloc[0]
                
                c_a, c_b = st.columns(2)
                with c_a:
                    st.info(f"Libros: {fila['Detalle']}")
                    st.write(f"**Saldo:** ${fila['Saldo']:,}")
                with c_b:
                    link_edit = f"{url_app}?rol=cliente&pedido_id={id_sel}"
                    msg_edit = f"Hola {fila['Cliente']}, aquí puedes corregir o ver tu pedido: {link_edit}"
                    st.link_button("📲 Reenviar Link de Edición (WhatsApp)", generar_link_whatsapp(fila['Celular'], msg_edit))
        else:
            st.info("No hay pedidos registrados aún.")

# --- ROUTER ---
params = st.query_params
if params.get("rol") == "cliente":
    vista_cliente(params.get("pedido_id"))
else:
    vista_admin()