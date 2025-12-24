import re

# Read the file
with open('content_quality_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the syntax error on line 596
content = re.sub(
    r'"word_count": word_count,n\s+"reading',
    '"word_count": word_count,\r\n                "reading',
    content
)

# Write back
with open('content_quality_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed syntax error!")
