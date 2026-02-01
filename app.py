import streamlit as st
import pandas as pd
import os
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
        # Estructura base
        return pd.DataFrame(columns=["Grado", "Area", "Libro", "Costo", "Precio Venta", "Ganancia"])

def guardar_inventario(df):
    # Asegurar que sean números y recalcular ganancia
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

# --- COMPONENTE DE SELECCIÓN DE LIBROS (Reutilizable) ---
def componente_seleccion_libros(inventario, key_suffix, seleccion_previa=None):
    grados = inventario['Grado'].unique()
    seleccion = []
    total = 0
    
    for grado in grados:
        df_grado = inventario[inventario['Grado'] == grado]
        with st.expander(f"📖 Libros de {grado}"):
            for index, row in df_grado.iterrows():
                key_check = f"{grado}_{row['Area']}_{row['Libro']}_{key_suffix}"
                label = f"{row['Area']} - {row['Libro']} (${int(row['Precio Venta']):,})"
                
                # Verificar si estaba seleccionado antes (para edición)
                checked = False
                if seleccion_previa and f"[{grado}] {row['Libro']}" in seleccion_previa:
                    checked = True
                
                if st.checkbox(label, key=key_check, value=checked):
                    seleccion.append(f"[{grado}] {row['Libro']}")
                    total += row['Precio Venta']
    return seleccion, total

# --- VISTA 1: CLIENTE (PÚBLICA) ---
def vista_cliente(pedido_id=None):
    st.image("https://cdn-icons-png.flaticon.com/512/2232/2232688.png", width=60)
    st.title("📚 Formulario de Pedido")
    st.caption("No requiere usuario ni contraseña.")
    
    inventario = cargar_inventario()
    if inventario.empty:
        st.error("El sistema no tiene libros cargados.")
        return

    # Lógica de Edición
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
        st.subheader("Selección de Libros")
        items, total = componente_seleccion_libros(inventario, "cli", datos_previos.get('Detalle', ''))
        
        st.divider()
        st.metric("Total a Pagar", f"${total:,.0f}")
        
        st.subheader("Pago")
        tipo = st.radio("Método:", ["Pago Total", "Abono Parcial", "Pago Contraentrega"], horizontal=True)
        abono = st.number_input("Valor a transferir hoy:", min_value=0.0, step=1000.0, value=float(datos_previos.get('Abonado', 0)))
        archivo = st.file_uploader("Comprobante (Imagen)", type=['jpg','png','jpeg','pdf'])

        if st.form_submit_button("✅ ENVIAR PEDIDO"):
            if not nombre or not celular:
                st.error("Falta Nombre o Celular")
            elif total == 0:
                st.error("Seleccione libros")
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
    # --- CONFIGURACIÓN DE URL EN BARRA LATERAL (SOLUCIÓN DEFINITIVA) ---
    st.sidebar.header("⚙️ Configuración")
    url_app = st.sidebar.text_input("Pega aquí el LINK de tu App Publicada:", 
                                    value="https://tu-app.streamlit.app", 
                                    help="Sin esto, los enlaces de WhatsApp no funcionarán.")
    
    menu = st.sidebar.radio("Menú Admin:", ["📊 Gestión de Pedidos", "➕ Ingreso Manual de Pedido", "📦 Inventario"])

    # ---------------- 1. INVENTARIO ----------------
    if menu == "📦 Inventario":
        st.title("📦 Inventario de Libros")
        
        # Carga Excel
        with st.expander("Subir Excel Masivo"):
            up = st.file_uploader("Excel (Grado, Area, Libro, Costo, Precio Venta)", type=['xlsx','csv'])
            if up:
                try:
                    df_up = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
                    guardar_inventario(df_up)
                    st.success("Cargado!")
                except: st.error("Error en archivo")
        
        # Editor
        df = cargar_inventario()
        if not df.empty:
            df_ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
            if st.button("Guardar Inventario"):
                guardar_inventario(df_ed)
                st.rerun()
            
            # Totales
            st.write("---")
            st.subheader("Resumen Financiero por Grado")
            resumen = df.groupby("Grado")[["Costo", "Precio Venta", "Ganancia"]].sum().reset_index()
            st.dataframe(resumen, use_container_width=True)

    # ---------------- 2. INGRESO MANUAL (RECUPERADO) ----------------
    elif menu == "➕ Ingreso Manual de Pedido":
        st.title("➕ Crear Pedido Manualmente")
        st.caption("Usa esta opción para registrar ventas telefónicas o presenciales (tu digitas por el cliente).")
        
        inventario = cargar_inventario()
        if inventario.empty:
            st.warning("Primero carga el inventario.")
        else:
            with st.form("form_manual_admin"):
                col1, col2 = st.columns(2)
                nombre = col1.text_input("Nombre Cliente")
                celular = col2.text_input("Celular")
                
                st.write("---")
                st.write("**Selecciona los libros:**")
                items, total = componente_seleccion_libros(inventario, "adm")
                
                st.write("---")
                c_tot, c_abo = st.columns(2)
                c_tot.metric("Total Pedido", f"${total:,.0f}")
                abono = c_abo.number_input("Abono Recibido ($):", min_value=0.0, step=1000.0)
                
                estado_inicial = st.selectbox("Estado Inicial:", ["Nuevo", "Pagado Total", "Entregado Inmediato"])

                if st.form_submit_button("💾 GUARDAR PEDIDO"):
                    if not nombre:
                        st.error("Falta el nombre.")
                    elif total == 0:
                        st.error("No seleccionaste libros.")
                    else:
                        df = cargar_pedidos()
                        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        nuevo_id = str(uuid.uuid4())[:8]
                        nuevo = {
                            "ID_Pedido": nuevo_id, "Fecha_Creacion": fecha, "Ultima_Modificacion": fecha,
                            "Cliente": nombre, "Celular": celular, "Detalle": " | ".join(items),
                            "Total": total, "Abonado": abono, "Saldo": total - abono, "Estado": estado_inicial,
                            "Comprobante": "Presencial/Manual", "Historial_Cambios": "Creado por Admin"
                        }
                        df = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
                        guardar_pedido_db(df)
                        st.success(f"Pedido guardado con ID: {nuevo_id}")

    # ---------------- 3. GESTIÓN PEDIDOS ----------------
    elif menu == "📊 Gestión de Pedidos":
        st.title("📊 Panel de Ventas")
        df = cargar_pedidos()
        
        # --- GENERADOR DE LINK (SOLUCIONADO) ---
        st.container(border=True)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📲 Enviar WhatsApp")
            tel = st.text_input("Celular Cliente:", key="tel_wa")
            if tel:
                if "tu-app" in url_app or "localhost" in url_app:
                    st.warning("⚠️ ¡OJO! Pega el link real de tu app en el menú de la izquierda para que esto funcione bien.")
                
                link_ped = f"{url_app}?rol=cliente"
                msg = f"Hola, haz tu pedido aquí: {link_ped}"
                link_wa = generar_link_whatsapp(tel, msg)
                st.link_button("Enviar Mensaje", link_wa)
        
        with c2:
            st.subheader("🔗 Copiar Link Genérico")
            st.code(f"{url_app}?rol=cliente", language="text")
            st.caption("Copia esto para grupos o redes sociales.")

        st.write("---")
        st.subheader("Listado de Pedidos")
        
        if not df.empty:
            filtro = st.text_input("Buscar Cliente:")
            if filtro:
                df = df[df['Cliente'].str.contains(filtro, case=False, na=False)]

            # Tabla Editable
            edited = st.data_editor(
                df,
                column_config={
                    "Estado": st.column_config.SelectboxColumn(options=["Nuevo", "Pagado", "En Impresión", "Entregado", "Anulado"], required=True),
                    "Total": st.column_config.NumberColumn(format="$%d"),
                    "Saldo": st.column_config.NumberColumn(format="$%d")
                },
                disabled=["ID_Pedido", "Detalle"],
                hide_index=True
            )
            if st.button("Actualizar Cambios"):
                guardar_pedido_db(edited)
                st.success("Guardado")
                st.rerun()

            # Gestión Individual
            st.write("---")
            st.write("**Gestión Detallada (Editar / Reenviar):**")
            p_sel = st.selectbox("Seleccionar:", df['ID_Pedido'] + " - " + df['Cliente'])
            if p_sel:
                id_sel = p_sel.split(" - ")[0]
                fila = df[df['ID_Pedido'] == id_sel].iloc[0]
                
                c_a, c_b = st.columns(2)
                with c_a:
                    st.info(f"Libros: {fila['Detalle']}")
                with c_b:
                    link_edit = f"{url_app}?rol=cliente&pedido_id={id_sel}"
                    msg_edit = f"Hola {fila['Cliente']}, corrige tu pedido aquí: {link_edit}"
                    st.link_button("Reenviar Link de Edición", generar_link_whatsapp(fila['Celular'], msg_edit))

        else:
            st.info("Sin pedidos.")

# --- ROUTER ---
params = st.query_params
if params.get("rol") == "cliente":
    vista_cliente(params.get("pedido_id"))
else:
    vista_admin()