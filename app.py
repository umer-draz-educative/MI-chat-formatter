
import streamlit as st
import json
import base64
from io import BytesIO
import tempfile
import os  # Add this import for os.chmod and os.path functions
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, ListItem, ListFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import markdown
import re
import requests
import subprocess
import shlex

# Initialize session state variables if they don't exist
if 'auth_header' not in st.session_state:
    st.session_state.auth_header = ''
if 'category' not in st.session_state:
    st.session_state.category = ''
if 'mi_id' not in st.session_state:
    st.session_state.mi_id = ''
if 'user_id' not in st.session_state:
    st.session_state.user_id = ''
if 'session_num' not in st.session_state:
    st.session_state.session_num = ''
if 'cookies' not in st.session_state:
    st.session_state.cookies = ''
if 'curl_parsed' not in st.session_state:
    st.session_state.curl_parsed = False

# Function to update session state
def update_session_state():
    # This ensures all form values are saved to session state
    st.session_state.category = st.session_state.category_input
    st.session_state.mi_id = st.session_state.mi_id_input
    st.session_state.user_id = st.session_state.user_id_input
    st.session_state.session_num = st.session_state.session_num_input

st.title("MI Viewer")

# Create tabs
tab1, tab2 = st.tabs(["Paste JSON", "Fetch from API"])

# Function to process and display chat data
def process_chat_data(data, source="JSON"):
    # Create a list to store content for PDF
    pdf_content = []
    styles = getSampleStyleSheet()
    
    # Add custom styles for markdown elements (only if they don't exist)
    if 'Code' not in styles:
        styles.add(ParagraphStyle(
            name='Code',
            parent=styles['Normal'],
            fontName='Courier',
            fontSize=9,
            backColor=colors.lightgrey,
            leftIndent=20,
            rightIndent=20
        ))
    
    # Add API information to the top of PDF if fetched from API
    if source == "API":
        # Add API information header
        pdf_content.append(Paragraph("<b>API Information:</b>", styles["Heading2"]))
        api_info = [
            f"Category: {st.session_state.category}",
            f"MI ID: {st.session_state.mi_id}",
            f"User ID: {st.session_state.user_id}",
            f"Session Number: {st.session_state.session_num}",
            f"API URL: https://www.educative.io/api/user/mock-interview/{st.session_state.category}/{st.session_state.mi_id}/{st.session_state.user_id}/{st.session_state.session_num}"
        ]
        
        # Add message count if available
        if "chat" in data:
            api_info.append(f"Number of Messages: {len(data['chat'])}")
        
        # Add each info line
        for info in api_info:
            pdf_content.append(Paragraph(info, styles["Normal"]))
        
        # Add spacer
        pdf_content.append(Spacer(1, 20))
        pdf_content.append(Paragraph("<b>Conversation:</b>", styles["Heading2"]))
    
    # Display chat messages
    if "chat" in data:
        for message in data["chat"]:
            # Determine message type and set styling
            is_ai = message.get("type") == "ai"
            
            # Create message container with different styling based on sender
            with st.container():
                # Add visual indicator for message type
                st.markdown(f"**{'AI' if is_ai else 'Human'}**:")
                
                # Add to PDF content
                pdf_content.append(Paragraph(f"<b>{'AI' if is_ai else 'Human'}:</b>", styles["Heading3"]))
                
                # Handle content based on type
                content = message.get("content", "")
                content_type = message.get("contentType", "text")
                
                if content_type == "text" or is_ai:
                    st.markdown(content)
                    
                    # Process markdown for PDF
                    # Handle lists
                    list_items = []
                    in_list = False
                    list_type = None
                    paragraphs = []
                    
                    for line in content.split('\n'):
                        # Check for code blocks
                        if line.strip().startswith('```') or line.strip().startswith('~~~'):
                            if in_list and list_items:
                                # End the current list before code block
                                if list_type == 'ul':
                                    paragraphs.append(ListFlowable(list_items, bulletType='bullet'))
                                else:
                                    paragraphs.append(ListFlowable(list_items, bulletType='1'))
                                list_items = []
                                in_list = False
                            
                            # Handle code block
                            paragraphs.append(Paragraph(line, styles["Code"]))
                            continue
                            
                        # Check for list items
                        ul_match = re.match(r'^\s*[\*\-\+]\s+(.+)$', line)
                        ol_match = re.match(r'^\s*\d+\.\s+(.+)$', line)
                        
                        if ul_match:
                            if not in_list or list_type != 'ul':
                                # End previous list if it was a different type
                                if in_list and list_items:
                                    if list_type == 'ol':
                                        paragraphs.append(ListFlowable(list_items, bulletType='1'))
                                    list_items = []
                                in_list = True
                                list_type = 'ul'
                            list_items.append(ListItem(Paragraph(ul_match.group(1), styles["Normal"])))
                        elif ol_match:
                            if not in_list or list_type != 'ol':
                                # End previous list if it was a different type
                                if in_list and list_items:
                                    if list_type == 'ul':
                                        paragraphs.append(ListFlowable(list_items, bulletType='bullet'))
                                    list_items = []
                                in_list = True
                                list_type = 'ol'
                            list_items.append(ListItem(Paragraph(ol_match.group(1), styles["Normal"])))
                        else:
                            # Regular paragraph - end any current list
                            if in_list and list_items:
                                if list_type == 'ul':
                                    paragraphs.append(ListFlowable(list_items, bulletType='bullet'))
                                else:
                                    paragraphs.append(ListFlowable(list_items, bulletType='1'))
                                list_items = []
                                in_list = False
                            
                            # Skip empty lines
                            if line.strip():
                                # Handle headers
                                header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
                                if header_match:
                                    level = len(header_match.group(1))
                                    header_text = header_match.group(2)
                                    style_name = f"Heading{min(level+1, 6)}"
                                    paragraphs.append(Paragraph(header_text, styles[style_name]))
                                else:
                                    # Handle bold and italic
                                    line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
                                    line = re.sub(r'\*(.+?)\*', r'<i>\1</i>', line)
                                    line = re.sub(r'\_\_(.+?)\_\_', r'<b>\1</b>', line)
                                    line = re.sub(r'\_(.+?)\_', r'<i>\1</i>', line)
                                    
                                    # Handle inline code
                                    line = re.sub(r'`(.+?)`', r'<font face="Courier" size="9">\1</font>', line)
                                    
                                    paragraphs.append(Paragraph(line, styles["Normal"]))
                    
                    # Add any remaining list items
                    if in_list and list_items:
                        if list_type == 'ul':
                            paragraphs.append(ListFlowable(list_items, bulletType='bullet'))
                        else:
                            paragraphs.append(ListFlowable(list_items, bulletType='1'))
                    
                    # Add all paragraphs to PDF content
                    pdf_content.extend(paragraphs)
                    
                elif content_type == "image" and not is_ai:
                    # Display base64 image
                    try:
                        content = message.get("drawingContent", "")
                        content = content.get("blob","").replace("data:image/png;base64,","")
                        image_data = base64.b64decode(content)
                        st.image(BytesIO(image_data))
                        
                        # Save image for PDF
                        img_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                        img_temp.write(image_data)
                        img_temp.close()

                        # Create image with preserved aspect ratio
                        img = Image(img_temp.name)
                        # Set a maximum width and let ReportLab calculate the height
                        max_width = 400
                        img_width, img_height = img.imageWidth, img.imageHeight
                        aspect = img_height / float(img_width)
                        img.drawWidth = max_width
                        img.drawHeight = max_width * aspect
                        pdf_content.append(img)
                    except Exception as e:
                        st.error(f"Failed to decode image: {e}")
                
                # Add separator between messages
                st.markdown("---")
                pdf_content.append(Spacer(1, 12))
        
        # Create PDF
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
        doc.build(pdf_content)
        
        # Clean up temporary image files
        for item in pdf_content:
            if isinstance(item, Image) and os.path.exists(item.filename):
                os.unlink(item.filename)
        
        # Offer PDF download
        pdf_data = pdf_buffer.getvalue()
        b64_pdf = base64.b64encode(pdf_data).decode('utf-8')
        href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="chat_transcript.pdf">Download PDF</a>'
        st.markdown(href, unsafe_allow_html=True)
    else:
        st.error("No chat data found in the JSON")

# Tab 1: Paste JSON
with tab1:
    # Text area for JSON input
    json_input = st.text_area("Paste your JSON chat data here:", height=200)

    # Add a button to trigger conversion
    if st.button("Convert JSON"):
        if json_input:
            try:
                # Parse JSON
                data = json.loads(json_input)
                process_chat_data(data, source="JSON")
            except json.JSONDecodeError:
                st.error("Invalid JSON format. Please check your input.")
            except Exception as e:
                st.error(f"Error processing data: {e}")

# Tab 2: Fetch from API
with tab2:
    st.subheader("Fetch from Educative API")
    
    # cURL input
    curl_command = st.text_area("Paste your cURL command here:", 
                               help="Copy the cURL command from browser network tab")
    
    # Parse button
    if st.button("Execute cURL"):
        if curl_command:
            try:
                with st.spinner("Executing cURL command..."):
                    # Save the curl command to a temporary file
                    curl_file = tempfile.NamedTemporaryFile(delete=False, suffix='.sh')
                    curl_file.write(curl_command.encode('utf-8'))
                    curl_file.close()
                    
                    # Make the file executable
                    os.chmod(curl_file.name, 0o755)
                    
                    # Execute the curl command and capture the output
                    process = subprocess.Popen(
                        ['bash', curl_file.name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate()
                    
                    # Clean up the temporary file
                    os.unlink(curl_file.name)
                    
                    if process.returncode == 0:
                        # Try to parse the output as JSON
                        try:
                            response_data = json.loads(stdout.decode('utf-8'))
                            
                            # Extract user ID if available
                            if "id" in response_data:
                                st.session_state.user_id = str(response_data["id"])
                            
                            # Extract cookies from the curl command
                            if "-b '" in curl_command or "-b \"" in curl_command:
                                cookie_start = curl_command.find("-b '") + 4 if "-b '" in curl_command else curl_command.find("-b \"") + 4
                                cookie_end = curl_command.find("'", cookie_start) if "-b '" in curl_command else curl_command.find("\"", cookie_start)
                                cookies = curl_command[cookie_start:cookie_end]
                                
                                st.session_state.cookies = cookies
                                st.session_state.auth_header = f"Cookie: {cookies}"
                                st.session_state.curl_parsed = True
                            
                            # Show success message
                            st.success("cURL executed successfully!")
                            st.json(response_data)
                            st.info("Authentication information extracted. Please fill in the remaining fields below.")
                            
                        except json.JSONDecodeError:
                            # Not JSON, just show the raw output
                            st.text_area("cURL Output", stdout.decode('utf-8'))
                            
                            # Still try to extract cookies
                            if "-b '" in curl_command or "-b \"" in curl_command:
                                cookie_start = curl_command.find("-b '") + 4 if "-b '" in curl_command else curl_command.find("-b \"") + 4
                                cookie_end = curl_command.find("'", cookie_start) if "-b '" in curl_command else curl_command.find("\"", cookie_start)
                                cookies = curl_command[cookie_start:cookie_end]
                                
                                st.session_state.cookies = cookies
                                st.session_state.auth_header = f"Cookie: {cookies}"
                                st.session_state.curl_parsed = True
                                
                                st.success("Cookies extracted successfully!")
                    else:
                        st.error(f"cURL command failed with error: {stderr.decode('utf-8')}")
                        
                        # Still try to extract cookies
                        if "-b '" in curl_command or "-b \"" in curl_command:
                            cookie_start = curl_command.find("-b '") + 4 if "-b '" in curl_command else curl_command.find("-b \"") + 4
                            cookie_end = curl_command.find("'", cookie_start) if "-b '" in curl_command else curl_command.find("\"", cookie_start)
                            cookies = curl_command[cookie_start:cookie_end]
                            
                            st.session_state.cookies = cookies
                            st.session_state.auth_header = f"Cookie: {cookies}"
                            st.session_state.curl_parsed = True
                            
                            st.success("Cookies extracted successfully despite cURL error!")
                    
            except Exception as e:
                st.error(f"Error executing cURL: {e}")
                st.session_state.curl_parsed = False
    
    # Display current values and allow manual editing
    st.subheader("API Parameters")
    st.info("Please fill in these values to fetch the mock interview data")

    col1, col2 = st.columns(2)
    with col1:
        category = st.text_input(
            "Category", 
            value=st.session_state.get("category", ""),
            key="category_input",
            help="e.g., 'system-design', 'coding', etc."
        )
        
        mi_id = st.text_input(
            "MI ID",
            value=st.session_state.get("mi_id", ""),
            key="mi_id_input",
            help="The mock interview identifier"
        )
    with col2:
        user_id = st.text_input(
            "User ID",
            value=st.session_state.get("user_id", ""),
            key="user_id_input",
            help="The user ID from the mock interview URL (may differ from account ID)"
        )
        
        session_num = st.text_input(
            "Session Number",
            value=st.session_state.get("session_num", ""),
            key="session_num_input",
            help="Usually '1' for the first session"
        )

    # Update session state with form values
    st.session_state.category = st.session_state.category_input
    st.session_state.mi_id = st.session_state.mi_id_input
    st.session_state.user_id = st.session_state.user_id_input
    st.session_state.session_num = st.session_state.session_num_input

    # Auth header (hidden by default)
    if st.checkbox("Show Authentication Information"):
        st.text_area("Cookie Information", value=st.session_state.cookies, disabled=True, height=100)

    # Fetch button
    if st.button("Fetch and Convert"):
        # Check which fields are missing
        missing = []
        if not st.session_state.auth_header: missing.append("Authentication")
        if not st.session_state.category: missing.append("Category")
        if not st.session_state.mi_id: missing.append("MI ID")
        if not st.session_state.user_id: missing.append("User ID")
        if not st.session_state.session_num: missing.append("Session Number")
        
        # Show warning for missing fields but continue anyway
        if missing:
            st.warning(f"Some fields are missing: {', '.join(missing)}. Attempting to fetch data anyway.")
        
        # Proceed with the request regardless
        try:
            # Use default values for missing fields
            category = st.session_state.category or "coding"  # Default to coding
            mi_id = st.session_state.mi_id or ""
            user_id = st.session_state.user_id or ""
            session_num = st.session_state.session_num or "1"  # Default to session 1
            
            # Construct API URL
            api_url = f"https://www.educative.io/api/user/mock-interview/{category}/{mi_id}/{user_id}/{session_num}"
            
            # Set up headers
            headers = {"Cookie": st.session_state.cookies} if st.session_state.cookies else {}
            
            # Make API request
            with st.spinner("Fetching data from API..."):
                st.info(f"Requesting: {api_url}")
                response = requests.get(api_url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    st.success("Data fetched successfully!")
                    process_chat_data(data, source="API")
                else:
                    st.error(f"API request failed with status code {response.status_code}")
                    st.text(f"Response: {response.text}")
                    
                    # Provide guidance based on error
                    if response.status_code == 401:
                        st.error("Authentication error. Please check your cookies/authentication information.")
                    elif response.status_code == 404:
                        st.error("Resource not found. Please check your Category, MI ID, User ID, and Session Number.")
        except Exception as e:
            st.error(f"Error fetching or processing data: {e}")
