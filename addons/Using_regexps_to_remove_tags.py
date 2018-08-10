"""Copyright: Arthur Milchior arthur@milchior.fr
License: GNU GPL, version 3 or later; http://www.gnu.org/copyleft/gpl.html
Feel free to contribute to this code on https://github.com/Arthur-Milchior/anki-css


Allows to use regexps in the "remove tags" box, in the browser.
"""


from anki.tags import TagManager
from anki.utils import intTime, ids2str, json
from anki.hooks import runHook
import re
debugTags=False
def debug(s, args):
        if debugTags:
                args = [a.encode('utf-8') for a in args ]
                debug (s.encode('utf-8')%args)

def remFromStr(self, deltags, tags):
        "Delete tags if they exist."
        debug("remFromStr\ndeltags:%s\ntags:%s",(deltags,tags))
        def wildcard(pat, str):
            debug ("wildcard\npat:%s\nstr:%s",(pat,str))
            pat = re.escape(pat).replace('\\*', '.*')
            debug ("pat':%s",pat)
            res = re.search(pat, str, re.IGNORECASE)
            if res:
                debug( "yes\n-------", [])
            else:
                debug( "no\n-------",[])
            return res
        currentTags = self.split(tags)
        for tag in self.split(deltags):
            # find tags, ignoring case
            remove = []
            for tx in currentTags:
                if (tag.lower() == tx.lower()) or wildcard(tag, tx):
                    remove.append(tx)
            # remove them
            for r in remove:
                currentTags.remove(r)
        debug ("currentTags%s",(str(currentTags)))
        return self.join(currentTags)

def bulkAdd(self, ids, tags, add=True):
        """Add tags in bulk. TAGS is space-separated. 

        keyword arguments
        ids -- a list of id
        tags -- a string of space-separated tag
        add -- whether to add (True) or to remove (False)
        """
        debug ("bulkAdd\nids:%s\ntags:%s\nadd:%s\n-------",(str(ids),str(tags),str(add)))
        newTags = self.split(tags)
        if not newTags:
            return
        # cache tag names
        if add:
            self.register(newTags)
        # find notes missing the tags
        if add:
            l = "tags not "
            fn = self.addToStr
        else:
            l = "tags "
            fn = self.remFromStr
        lim = " or ".join(
            [l+"like :_%d" % c for c, t in enumerate(newTags)])
        res = self.col.db.all(
            "select id, tags from notes where id in %s and (%s)" % (
                ids2str(ids), lim),
            **dict([("_%d" % x, '%% %s %%' % y.replace('*', '%'))
                    for x, y in enumerate(newTags)]))
        # update tags
        nids = []
        def fix(row):
            nids.append(row[0])
            return {'id': row[0], 't': fn(tags, row[1]), 'n':intTime(),
                'u':self.col.usn()}
        self.col.db.executemany(
            "update notes set tags=:t,mod=:n,usn=:u where id = :id",
            [fix(row) for row in res])

TagManager.remFromStr = remFromStr
TagManager.bulkAdd = bulkAdd
