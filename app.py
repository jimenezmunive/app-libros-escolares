import streamlit as st
import pandas as pd
import os
from datetime import datetime
import uuid

# --- CONFIGURACIÓN CLAVE (¡REEMPLAZAR CON TU LINK FINAL!) ---
# Una vez publiques la app, pega aquí el enlace real.
# Ejemplo: "https://libros-escolares.streamlit.app"
URL_REAL_APP = "https://tu-app-aqui.streamlit.app" 

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

# --- FUNCIONES AUXILIARES ---
def generar_link_whatsapp(celular, mensaje):
    celular = str(celular).replace(" ", "").replace("+", "").strip()
    if not celular.startswith("57"): 
        celular = "57" + celular
    texto_codificado = mensaje.replace(" ", "%20").replace("\n", "%0A")
    return f"https://wa.me/{celular}?text={texto_codificado}"

# --- VISTA: CLIENTE (ACCESO PÚBLICO - SIN LOGIN) ---
def vista_cliente(pedido_id=None):
    st.image("https://cdn-icons-png.flaticon.com/512/2232/2232688.png", width=60)
    st.title("📚 Formulario de Pedido Escolar")
    st.caption("Complete la información a continuación. No requiere usuario ni contraseña.")
    
    inventario = cargar_inventario()
    if inventario.empty:
        st.error("El sistema no tiene libros cargados. Contacte al administrador.")
        return

    # Cargar datos previos si es modificación
    datos_previos = {}
    es_modificacion = False
    
    if pedido_id:
        df_pedidos = cargar_pedidos()
        pedido_existente = df_pedidos[df_pedidos['ID_Pedido'] == pedido_id]
        if not pedido_existente.empty:
            datos_previos = pedido_existente.iloc[0].to_dict()
            es_modificacion = True
            st.info(f"📝 Modificando pedido del: {datos_previos['Fecha_Creacion']}")

    with st.form("form_pedido_cliente"):
        col_datos1, col_datos2 = st.columns(2)
        nombre = col_datos1.text_input("Nombre Completo", value=datos_previos.get('Cliente', ''))
        celular = col_datos2.text_input("Celular (WhatsApp)", value=datos_previos.get('Celular', ''))

        st.divider()
        st.subheader("Selección de Libros")
        
        grados = inventario['Grado'].unique()
        seleccion_libros = []
        total_compra = 0
        detalle_previo = datos_previos.get('Detalle', '')
        
        for grado in grados:
            df_grado = inventario[inventario['Grado'] == grado]
            with st.expander(f"📖 Libros de {grado}"):
                for index, row in df_grado.iterrows():
                    key_check = f"{grado}_{row['Area']}_{row['Libro']}"
                    label = f"{row['Area']} - {row['Libro']} (${int(row['Precio Venta']):,})"
                    
                    checked = False
                    if es_modificacion and f"[{grado}] {row['Libro']}" in detalle_previo:
                        checked = True
                    
                    if st.checkbox(label, key=key_check, value=checked):
                        seleccion_libros.append(f"[{grado}] {row['Libro']}")
                        total_compra += row['Precio Venta']
        
        st.divider()
        st.metric("💰 Total a Pagar", f"${total_compra:,.0f}")
        
        st.subheader("Confirmación de Pago")
        tipo_pago = st.radio("Método de pago", ["Pago Total", "Abono Parcial", "Pago Contraentrega"], index=0)
        
        val_abono = 0
        if tipo_pago in ["Pago Total", "Abono Parcial"]:
            val_abono = st.number_input("Valor a transferir:", min_value=0.0, step=1000.0, value=float(datos_previos.get('Abonado', 0)))
            st.write("Adjuntar comprobante (Opcional si es pago en efectivo):")
            archivo = st.file_uploader("Subir Imagen/PDF", type=['jpg', 'png', 'pdf'])
        else:
            archivo = None

        enviar = st.form_submit_button("✅ CONFIRMAR PEDIDO")

        if enviar:
            if not nombre or not celular:
                st.error("⚠️ Falta Nombre o Celular.")
            elif total_compra == 0:
                st.error("⚠️ Seleccione al menos un libro.")
            else:
                df_pedidos = cargar_pedidos()
                fecha_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                saldo = total_compra - val_abono
                
                if es_modificacion:
                    idx = df_pedidos[df_pedidos['ID_Pedido'] == pedido_id].index
                    if not idx.empty:
                        df_pedidos.at[idx[0], 'Ultima_Modificacion'] = fecha_now
                        df_pedidos.at[idx[0], 'Detalle'] = " | ".join(seleccion_libros)
                        df_pedidos.at[idx[0], 'Total'] = total_compra
                        df_pedidos.at[idx[0], 'Abonado'] = val_abono
                        df_pedidos.at[idx[0], 'Saldo'] = saldo
                        df_pedidos.at[idx[0], 'Historial_Cambios'] = str(df_pedidos.at[idx[0], 'Historial_Cambios']) + f" | Modif: {fecha_now}"
                        if archivo:
                            df_pedidos.at[idx[0], 'Comprobante'] = "Nuevo Comprobante"
                        guardar_pedido_db(df_pedidos)
                        st.success("✅ Pedido Actualizado.")
                else:
                    nuevo_id = str(uuid.uuid4())[:8]
                    nuevo_pedido = {
                        "ID_Pedido": nuevo_id,
                        "Fecha_Creacion": fecha_now,
                        "Ultima_Modificacion": fecha_now,
                        "Cliente": nombre,
                        "Celular": celular,
                        "Detalle": " | ".join(seleccion_libros),
                        "Total": total_compra,
                        "Abonado": val_abono,
                        "Saldo": saldo,
                        "Estado": "Nuevo",
                        "Comprobante": "Si" if archivo else "No",
                        "Historial_Cambios": "Original"
                    }
                    df_new = pd.DataFrame([nuevo_pedido])
                    df_pedidos = pd.concat([df_pedidos, df_new], ignore_index=True)
                    guardar_pedido_db(df_pedidos)
                    st.success(f"✅ ¡Pedido Enviado! ID: {nuevo_id}")
                    st.balloons()

# --- VISTA: ADMINISTRADOR ---
def vista_admin():
    st.sidebar.header("Panel Administrador")
    menu = st.sidebar.radio("Ir a:", ["📊 Gestión de Pedidos", "📦 Inventario de Libros"])

    if menu == "📦 Inventario de Libros":
        st.title("📦 Inventario")
        with st.expander("📂 Subir Excel Masivo"):
            archivo_excel = st.file_uploader("Archivo Excel (Grado, Area, Libro, Costo, Precio Venta)", type=['xlsx', 'csv'])
            if archivo_excel:
                try:
                    if archivo_excel.name.endswith('.csv'): df_upload = pd.read_csv(archivo_excel)
                    else: df_upload = pd.read_excel(archivo_excel)
                    guardar_inventario(df_upload)
                    st.success("Inventario cargado.")
                except Exception as e:
                    st.error(f"Error: {e}")

        st.divider()
        df_inv = cargar_inventario()
        if not df_inv.empty:
            df_editado = st.data_editor(df_inv, num_rows="dynamic", use_container_width=True)
            if st.button("💾 Guardar Inventario"):
                guardar_inventario(df_editado)
                st.success("Guardado.")
                st.rerun()
            
            st.caption("Resumen Financiero:")
            resumen = df_inv.groupby("Grado")[["Costo", "Precio Venta", "Ganancia"]].sum().reset_index()
            st.dataframe(resumen, use_container_width=True)

    elif menu == "📊 Gestión de Pedidos":
        st.title("Panel de Ventas")
        df_pedidos = cargar_pedidos()
        
        # --- HERRAMIENTA WHATSAPP MEJORADA ---
        st.container(border=True)
        st.subheader("📲 Enviar Enlace a Cliente")
        
        col_w1, col_w2 = st.columns([1, 1])
        with col_w1:
            st.markdown("##### Opción 1: Enviar a un número")
            tel_nuevo = st.text_input("Celular del Cliente:", placeholder="Ej: 3001234567")
            if tel_nuevo:
                link_gen = f"{URL_REAL_APP}?rol=cliente"
                mensaje = f"Hola! Realiza tu pedido escolar aquí: {link_gen}"
                link_wa = generar_link_whatsapp(tel_nuevo, mensaje)
                # Usamos link_button para que parezca un botón real
                st.link_button("📤 Enviar WhatsApp Ahora", link_wa)
                st.caption("ℹ️ El cliente NO necesita descargar la app ni registrarse.")

        with col_w2:
            st.markdown("##### Opción 2: Copiar Enlace General")
            st.write("Usa este botón para copiar el link y pegarlo en grupos:")
            # st.code genera una caja con un botón de copiar nativo a la derecha
            st.code(f"{URL_REAL_APP}?rol=cliente", language="text")
            st.caption("👆 Haz clic en el icono de 'hojas' a la derecha para copiar.")

        st.divider()
        
        # --- TABLA DE PEDIDOS ---
        st.subheader("📋 Pedidos Registrados")
        if not df_pedidos.empty:
            edited_df = st.data_editor(
                df_pedidos,
                column_config={
                    "Estado": st.column_config.SelectboxColumn(options=["Nuevo", "Pagado", "En Impresión", "Entregado", "Anulado"], required=True),
                    "Total": st.column_config.NumberColumn(format="$%d"),
                    "Saldo": st.column_config.NumberColumn(format="$%d")
                },
                disabled=["ID_Pedido", "Detalle"],
                hide_index=True
            )
            if st.button("💾 Actualizar Estados"):
                guardar_pedido_db(edited_df)
                st.success("Estados actualizados.")
            
            st.divider()
            st.write("**Modificar / Reenviar Pedido:**")
            pedido_sel = st.selectbox("Seleccionar Pedido:", df_pedidos['ID_Pedido'] + " | " + df_pedidos['Cliente'])
            if pedido_sel:
                id_sel = pedido_sel.split(" | ")[0]
                fila = df_pedidos[df_pedidos['ID_Pedido'] == id_sel].iloc[0]
                
                c1, c2 = st.columns(2)
                with c1:
                    link_edit = f"{URL_REAL_APP}?rol=cliente&pedido_id={id_sel}"
                    msg = f"Hola {fila['Cliente']}, edita tu pedido aquí: {link_edit}"
                    st.link_button("📲 Reenviar Link de Edición", generar_link_whatsapp(fila['Celular'], msg))
                with c2:
                    st.info(f"Historial: {fila['Historial_Cambios']}")
        else:
            st.info("Sin pedidos aún.")

# --- ROUTING ---
params = st.query_params
rol = params.get("rol", "admin")
pedido_id_url = params.get("pedido_id", None)

if rol == "cliente":
    vista_cliente(pedido_id_url)
else:
    vista_admin()