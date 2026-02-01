import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Venta Libros Escolares", layout="wide", initial_sidebar_state="collapsed")

# Nombre del archivo donde se guardarán los datos
ARCHIVO_PEDIDOS = 'pedidos_db.csv'

# --- INVENTARIO DE LIBROS (MODIFICA LOS PRECIOS AQUÍ) ---
INVENTARIO = {
    "Grado 1": {"Matemáticas": 50000, "Español": 45000, "Inglés": 48000, "Ciencias": 42000},
    "Grado 2": {"Matemáticas": 52000, "Español": 46000, "Inglés": 49000, "Ciencias": 43000},
    "Grado 3": {"Matemáticas": 55000, "Español": 48000, "Inglés": 50000, "Ciencias": 45000},
    "Grado 4": {"Matemáticas": 56000, "Español": 49000, "Inglés": 51000, "Ciencias": 46000},
    "Grado 5": {"Matemáticas": 58000, "Español": 50000, "Inglés": 52000, "Ciencias": 48000},
    # Puedes seguir agregando grados...
    "Grado 11": {"Física": 65000, "Química": 65000, "Cálculo": 70000, "Filosofía": 40000}
}

# --- FUNCIONES DEL SISTEMA ---
def cargar_datos():
    """Carga la base de datos o crea una nueva si no existe."""
    if not os.path.exists(ARCHIVO_PEDIDOS):
        return pd.DataFrame(columns=[
            "ID", "Fecha", "Cliente", "Celular", "Detalle_Pedido", 
            "Total_Pagar", "Abonado", "Saldo_Pendiente", 
            "Estado", "Porcentaje_Pago"
        ])
    return pd.read_csv(ARCHIVO_PEDIDOS)

def guardar_datos(df):
    """Guarda los datos en el archivo CSV."""
    df.to_csv(ARCHIVO_PEDIDOS, index=False)

# --- INTERFAZ PARA EL CLIENTE (MÓVIL) ---
def interfaz_cliente():
    st.image("https://cdn-icons-png.flaticon.com/512/2232/2232688.png", width=80)
    st.title("📚 Pedido de Textos Escolares")
    st.write("Seleccione los libros que necesita. Puede mezclar grados.")

    with st.form("formulario_pedido"):
        st.subheader("1. Tus Datos")
        col_a, col_b = st.columns(2)
        nombre = col_a.text_input("Nombre Completo *")
        celular = col_b.text_input("Celular (WhatsApp) *")

        st.subheader("2. Selección de Libros")
        items_seleccionados = []
        total = 0
        
        # Mostrar libros por grado en menús desplegables
        for grado, materias in INVENTARIO.items():
            with st.expander(f"Ver libros de {grado}"):
                for materia, precio in materias.items():
                    # Checkbox único para cada libro
                    if st.checkbox(f"{materia} (${precio:,.0f})", key=f"{grado}_{materia}"):
                        items_seleccionados.append(f"[{grado}] {materia}")
                        total += precio
        
        st.info(f"💰 **Total del Pedido:** ${total:,.0f}")
        
        st.subheader("3. Pago y Confirmación")
        tipo_pago = st.radio("¿Cómo realizarás el pago?", ["Pago Total", "Abono Parcial"])
        abono = st.number_input("Valor que vas a transferir hoy ($):", min_value=0, step=5000)
        
        st.write("Sube aquí la captura de tu transferencia:")
        archivo_pago = st.file_uploader("Comprobante de Pago", type=['jpg', 'png', 'jpeg', 'pdf'])

        confirmar = st.form_submit_button("✅ ENVIAR PEDIDO")

        if confirmar:
            if not nombre or not celular:
                st.error("⚠️ Falta tu nombre o celular.")
            elif total == 0:
                st.error("⚠️ No has seleccionado ningún libro.")
            elif abono == 0:
                st.error("⚠️ Debes indicar el valor del abono o pago.")
            elif not archivo_pago:
                st.error("⚠️ Por favor adjunta el comprobante de pago.")
            else:
                # Procesar pedido
                df = cargar_datos()
                saldo = total - abono
                porcentaje = (abono / total) * 100 if total > 0 else 0
                
                nuevo_registro = {
                    "ID": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Cliente": nombre,
                    "Celular": celular,
                    "Detalle_Pedido": " + ".join(items_seleccionados),
                    "Total_Pagar": total,
                    "Abonado": abono,
                    "Saldo_Pendiente": saldo,
                    "Estado": "Pendiente Revisión",
                    "Porcentaje_Pago": round(porcentaje, 1)
                }
                
                # Agregamos el nuevo pedido usando concat (método moderno de pandas)
                nuevo_df = pd.DataFrame([nuevo_registro])
                df = pd.concat([df, nuevo_df], ignore_index=True)
                guardar_datos(df)
                
                st.success("¡Pedido Recibido! Nos pondremos en contacto contigo.")
                st.balloons()

# --- INTERFAZ PARA EL ADMINISTRADOR (PC/TABLET) ---
def interfaz_admin():
    st.sidebar.title("Panel Administrador")
    st.title("📊 Gestión de Pedidos")

    df = cargar_datos()

    # --- MÉTRICAS SUPERIORES ---
    if not df.empty:
        total_ventas = df["Total_Pagar"].sum()
        total_recaudado = df["Abonado"].sum()
        total_por_cobrar = df["Saldo_Pendiente"].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Ventas Totales", f"${total_ventas:,.0f}")
        m2.metric("Dinero Recibido", f"${total_recaudado:,.0f}")
        m3.metric("Cartera (Por Cobrar)", f"${total_por_cobrar:,.0f}", delta_color="inverse")

    st.divider()

    # --- GENERADOR DE LINK WHATSAPP ---
    st.subheader("🔗 Enviar Link a Cliente")
    col1, col2 = st.columns([2, 1])
    
    # Aquí el admin pegará la URL de su app una vez la publique
    url_app = st.text_input("Pega aquí la URL de tu App publicada (ej: https://miapp.streamlit.app)", "http://localhost:8501")
    celular_cliente = col1.text_input("Número del Cliente (ej: 3001234567)")
    
    if celular_cliente:
        mensaje = f"Hola! Aquí tienes el enlace para hacer tu pedido de libros de forma fácil: {url_app}/?rol=cliente"
        link_wa = f"https://wa.me/57{celular_cliente}?text={mensaje.replace(' ', '%20')}"
        col2.write("") # Espacio
        col2.write("") # Espacio
        col2.markdown(f"[➡️ **Enviar WhatsApp**]({link_wa})", unsafe_allow_html=True)

    st.divider()

    # --- GESTIÓN DE PEDIDOS ---
    st.subheader("📋 Base de Datos")

    if not df.empty:
        # Editor de datos interactivo
        df_editado = st.data_editor(
            df,
            num_rows="dynamic",
            column_config={
                "Estado": st.column_config.SelectboxColumn(
                    "Estado",
                    options=["Pendiente Revisión", "En Impresión", "Entregado Parcial", "Entregado Total", "Devuelto"],
                    required=True,
                    width="medium"
                ),
                "Porcentaje_Pago": st.column_config.ProgressColumn(
                    "% Pago", format="%.1f%%", min_value=0, max_value=100
                ),
                "Total_Pagar": st.column_config.NumberColumn("Total", format="$%d"),
                "Abonado": st.column_config.NumberColumn("Abonado", format="$%d"),
                "Saldo_Pendiente": st.column_config.NumberColumn("Saldo", format="$%d"),
            },
            hide_index=True
        )

        if st.button("💾 Guardar Cambios en Base de Datos"):
            guardar_datos(df_editado)
            st.success("Cambios guardados correctamente.")
            st.rerun()

        # Botón Exportar
        st.download_button(
            label="📥 Descargar Excel/CSV",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name='reporte_libros.csv',
            mime='text/csv'
        )
        
        # --- ALERTAS DE MORA ---
        st.subheader("🚨 Alertas de Cobranza")
        hay_alertas = False
        for i, fila in df.iterrows():
            # Si se entregó Totalmente pero hay saldo pendiente
            if fila["Estado"] == "Entregado Total" and fila["Saldo_Pendiente"] > 0:
                st.warning(f"⚠️ OJO: El pedido de **{fila['Cliente']}** está ENTREGADO pero debe **${fila['Saldo_Pendiente']:,.0f}**.")
                hay_alertas = True
        
        if not hay_alertas:
            st.success("No hay alertas de mora en pedidos entregados.")

    else:
        st.info("Aún no hay pedidos registrados. Envía el link a tus clientes para comenzar.")

# --- CONTROLADOR DE VISTAS ---
# Esto decide si mostramos la vista Admin o Cliente
params = st.query_params
rol = params.get("rol", "admin")

if rol == "cliente":
    interfaz_cliente()
else:
    interfaz_admin()